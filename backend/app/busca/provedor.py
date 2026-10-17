"""Interface comum dos provedores de busca (especificação §8.1).

``BUSCA_PROVEDOR = "tavily" | "brave" | "searxng" | "falso"``. O código nunca
chama um provedor direto: usa ``buscar``, que conta os limites (20 buscas por
cadeia e 300 por usuário por dia) e passa pelo cache de 24 h no Redis.

Os limites contam **todo pedido de busca**, inclusive os que o cache responde:
eles existem tanto para o custo da chave da equipe quanto para segurar um
agente que entra em loop de buscas.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from redis.asyncio import Redis

NomeProvedor = Literal["tavily", "brave", "searxng", "duckduckgo", "falso"]

LIMITE_POR_CADEIA = 20
LIMITE_POR_USUARIO_DIA = 300
CACHE_SEGUNDOS = 24 * 60 * 60
PRAZO_SEGUNDOS = 15
SEARXNG_PADRAO = "http://localhost:8888"

SO_DESENVOLVIMENTO: frozenset[str] = frozenset({"falso", "searxng", "duckduckgo"})
"""Provedores que não sobem em produção: o ``falso`` inventa fontes, o SearXNG é só para
desenvolvimento local (§8.1) e o DuckDuckGo HTML não é uma API (limita quem busca muito)."""


class ResultadoBusca(BaseModel):
    titulo: str
    url: str
    trecho: str
    origem: str
    """Domínio do resultado (``g1.globo.com``): vai para a cerca e para os links do passo."""


class ProvedorBusca(Protocol):
    async def buscar(
        self, consulta: str, idioma: str = "pt-BR", limite: int = 5
    ) -> list[ResultadoBusca]: ...


class ErroBusca(Exception):
    """Falha do provedor (inclui o limite do mês da chave da equipe)."""


class LimiteDeBusca(ErroBusca):
    """Passou do limite de buscas da cadeia ou do usuário no dia."""


class BuscaProibidaEmProducao(ErroBusca):
    """``BUSCA_PROVEDOR`` de desenvolvimento (``falso``, ``searxng``) fora de dev/teste."""


def verificar_busca_permitida(nome: str, ambiente: str) -> None:
    """Recusa ``falso`` e ``searxng`` em produção (a mesma trava do modelo falso).

    Falha fechada: qualquer ``AMBIENTE`` que não seja ``desenvolvimento`` ou ``teste`` conta
    como produção. O worker chama na subida e ``obter_provedor`` chama de novo.
    """
    from app.core.config import ambiente_local

    if nome.strip().lower() in SO_DESENVOLVIMENTO and not ambiente_local(ambiente):
        raise BuscaProibidaEmProducao(
            f"BUSCA_PROVEDOR={nome} é só para desenvolvimento. "
            "Em produção use tavily ou brave e reinicie."
        )


def dominio(url: str) -> str:
    """Host da URL sem ``www.``."""
    host = urlsplit(url).hostname or ""
    return host.removeprefix("www.")


def obter_provedor(
    nome: str,
    *,
    chave: str | None = None,
    base_url: str | None = None,
    cliente: httpx.AsyncClient | None = None,
    ambiente: str | None = None,
) -> ProvedorBusca:
    """Devolve o provedor configurado (``BUSCA_PROVEDOR`` e ``BUSCA_CHAVE``).

    ``ambiente`` vem de ``AMBIENTE`` na configuração quando não é passado.
    """
    if ambiente is None:
        from app.core.config import obter_configuracao

        ambiente = obter_configuracao().ambiente
    verificar_busca_permitida(nome, ambiente)
    if nome == "tavily":
        from app.busca.tavily import BuscaTavily

        return BuscaTavily(_exigir_chave(nome, chave), cliente=cliente)
    if nome == "brave":
        from app.busca.brave import BuscaBrave

        return BuscaBrave(_exigir_chave(nome, chave), cliente=cliente)
    if nome == "searxng":
        from app.busca.searxng import BuscaSearxng

        return BuscaSearxng(base_url or SEARXNG_PADRAO, cliente=cliente)
    if nome == "duckduckgo":
        from app.busca.duckduckgo import BuscaDuckDuckGo

        return BuscaDuckDuckGo(cliente=cliente)
    if nome == "falso":
        from app.busca.falso import BuscaFalsa

        return BuscaFalsa()
    raise ErroBusca(f"Provedor de busca desconhecido: {nome!r}.")


def _exigir_chave(nome: str, chave: str | None) -> str:
    if not chave:
        raise ErroBusca(f"O provedor de busca {nome} precisa de BUSCA_CHAVE.")
    return chave


# ---------- HTTP comum aos provedores ----------


async def pedir_json(
    cliente: httpx.AsyncClient | None, provedor: str, metodo: str, url: str, **kwargs: Any
) -> Any:
    """Faz o pedido e traduz qualquer falha em ``ErroBusca`` com mensagem clara.

    A chave nunca entra na mensagem de erro.
    """
    proprio = cliente is None
    cliente = cliente or httpx.AsyncClient(timeout=PRAZO_SEGUNDOS, trust_env=False)
    try:
        resposta = await cliente.request(metodo, url, **kwargs)
    except httpx.TimeoutException as erro:
        raise ErroBusca(f"A busca ({provedor}) demorou demais.") from erro
    except httpx.HTTPError as erro:
        raise ErroBusca(f"Não consegui falar com a busca ({provedor}).") from erro
    finally:
        if proprio:
            await cliente.aclose()
    if resposta.status_code in (401, 403):
        raise ErroBusca(f"A chave da busca ({provedor}) foi recusada.")
    if resposta.status_code in (402, 429, 432, 433):
        raise ErroBusca(f"A busca ({provedor}) chegou no limite do plano. Siga com o que já tem.")
    if resposta.status_code >= 400:
        raise ErroBusca(f"A busca ({provedor}) respondeu {resposta.status_code}.")
    try:
        return resposta.json()
    except ValueError as erro:
        raise ErroBusca(f"A busca ({provedor}) devolveu uma resposta inválida.") from erro


def montar_resultados(
    itens: list[dict[str, Any]], *, titulo: str, url: str, trecho: str, limite: int
) -> list[ResultadoBusca]:
    """Converte os itens do provedor, pulando os que vierem sem URL."""
    resultados: list[ResultadoBusca] = []
    for item in itens:
        endereco = item.get(url)
        if not isinstance(endereco, str) or not endereco.startswith(("http://", "https://")):
            continue
        try:
            resultados.append(
                ResultadoBusca(
                    titulo=str(item.get(titulo) or endereco),
                    url=endereco,
                    trecho=str(item.get(trecho) or ""),
                    origem=dominio(endereco),
                )
            )
        except ValidationError:
            continue
        if len(resultados) == limite:
            break
    return resultados


# ---------- cache e limites ----------


def normalizar_consulta(consulta: str) -> str:
    return " ".join(consulta.lower().split())


def chave_cache(nome_provedor: str, consulta: str, idioma: str, limite: int) -> str:
    base = f"{nome_provedor}|{idioma}|{limite}|{normalizar_consulta(consulta)}"
    return "busca:cache:" + hashlib.sha256(base.encode()).hexdigest()


def chave_uso_dia(usuario_id: UUID, agora: datetime | None = None) -> str:
    """Contador do dia (UTC) do usuário."""
    dia = (agora or datetime.now(UTC)).strftime("%Y-%m-%d")
    return f"busca:uso:{usuario_id}:{dia}"


def chave_uso_cadeia(cadeia_id: UUID) -> str:
    return f"busca:cadeia:{cadeia_id}"


async def contar_busca(
    redis: Redis,
    usuario_id: UUID,
    cadeia_id: UUID | None = None,
    *,
    agora: datetime | None = None,
) -> None:
    """Soma uma busca e levanta ``LimiteDeBusca`` se passar de um dos limites."""
    pipe = redis.pipeline(transaction=True)
    chave_dia = chave_uso_dia(usuario_id, agora)
    pipe.incr(chave_dia)
    pipe.expire(chave_dia, 2 * 24 * 60 * 60)
    if cadeia_id is not None:
        chave_cadeia = chave_uso_cadeia(cadeia_id)
        pipe.incr(chave_cadeia)
        pipe.expire(chave_cadeia, 7 * 24 * 60 * 60)
    resultado = await pipe.execute()
    if int(resultado[0]) > LIMITE_POR_USUARIO_DIA:
        raise LimiteDeBusca(
            f"Você chegou no limite de {LIMITE_POR_USUARIO_DIA} buscas por dia. "
            "Siga com o que já tem."
        )
    if cadeia_id is not None and int(resultado[2]) > LIMITE_POR_CADEIA:
        raise LimiteDeBusca(
            f"Esta tarefa chegou no limite de {LIMITE_POR_CADEIA} buscas. Siga com o que já tem."
        )


async def buscar_com_cache(
    redis: Redis,
    provedor: ProvedorBusca,
    nome_provedor: str,
    consulta: str,
    idioma: str = "pt-BR",
    limite: int = 5,
) -> list[ResultadoBusca]:
    """Busca passando pelo cache do Redis (24 h por consulta)."""
    chave = chave_cache(nome_provedor, consulta, idioma, limite)
    guardado = await redis.get(chave)
    if guardado:
        return [ResultadoBusca.model_validate(item) for item in json.loads(guardado)]
    resultados = await provedor.buscar(consulta, idioma=idioma, limite=limite)
    await redis.set(
        chave,
        json.dumps([r.model_dump() for r in resultados], ensure_ascii=False),
        ex=CACHE_SEGUNDOS,
    )
    return resultados


async def buscar(
    redis: Redis,
    provedor: ProvedorBusca,
    nome_provedor: str,
    consulta: str,
    *,
    usuario_id: UUID,
    cadeia_id: UUID | None = None,
    idioma: str = "pt-BR",
    limite: int = 5,
) -> list[ResultadoBusca]:
    """Entrada única da busca: limites, depois cache, depois o provedor."""
    consulta = consulta.strip()
    if not consulta:
        raise ErroBusca("Consulta vazia.")
    await contar_busca(redis, usuario_id, cadeia_id)
    return await buscar_com_cache(redis, provedor, nome_provedor, consulta, idioma, limite)
