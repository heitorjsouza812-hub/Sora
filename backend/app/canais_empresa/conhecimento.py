"""Base de conhecimento da empresa: fusão de itens repetidos, contradição e busca.

- Itens parecidos (mesma categoria e título com palavras em comum) se fundem: soma a contagem e
  acrescenta a origem.
- Mesmo item com conteúdo diferente = **contradição**: o item fica marcado e o conteúdo mais
  recente vence (o anterior vai para ``anteriores``). Item editado pelo usuário (``travado``)
  nunca é sobrescrito: só conta.
- Item apagado pelo usuário não volta sozinho.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canais_empresa.extracao import MAX_CONTEUDO, MAX_TITULO, ConhecimentoExtraido
from app.canais_empresa.tabelas import ConhecimentoEmpresa

LIMITE_SEMELHANCA_TITULO = 0.7
LIMITE_SEMELHANCA_CONTEUDO = 0.4
MAX_ORIGENS = 20
MAX_ANTERIORES = 10

_PALAVRAS_VAZIAS = frozenset(
    "a o as os um uma uns umas de da do das dos em na no nas nos para por com sem que e ou se "
    "ao aos qual quais como quando onde isso essa esse esta este tem ter foi ser sao era mais "
    "muito voces voce meu minha seu sua nosso nossa vai vou pode podem posso favor".split()
)


def normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _radical(palavra: str) -> str:
    """ "trocar"/"troca"/"trocas" → "troca": junta as flexões mais comuns."""
    return palavra[:5] if len(palavra) >= 6 else palavra


def palavras(texto: str) -> set[str]:
    return {
        _radical(p)
        for p in re.findall(r"[a-z0-9]+", normalizar(texto))
        if len(p) >= 3 and p not in _PALAVRAS_VAZIAS
    }


def numeros(texto: str) -> set[str]:
    """Prazos, preços e quantidades citados: "7 dias", "R$ 29,90". É o que mais separa duas
    respostas que parecem iguais."""
    return {n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", texto)}


def mesmo_conteudo(a: str, b: str) -> bool:
    """Dois conteúdos dizem a mesma coisa? Números diferentes = contradição, mesmo com
    palavras parecidas; sem números vale a semelhança das palavras."""
    if numeros(a) != numeros(b):
        return False
    return semelhanca(palavras(a), palavras(b)) >= LIMITE_SEMELHANCA_CONTEUDO


def semelhanca(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def chave_de(categoria: str, titulo: str) -> str:
    return f"{categoria}:{' '.join(sorted(palavras(titulo))) or normalizar(titulo)}"[:300]


def _agora_iso(instante: datetime) -> str:
    return instante.astimezone(UTC).isoformat()


async def fundir(
    sessao: AsyncSession,
    usuario_id: UUID,
    itens: list[tuple[ConhecimentoExtraido, dict[str, Any], datetime]],
) -> tuple[int, int]:
    """Funde os itens extraídos na base. Cada item vem com a origem
    (``{canal, mensagem_id, externo_id, link, em, contato_id}``) e a data da mensagem.
    Devolve ``(novos, atualizados)``."""
    novos = atualizados = 0
    cache: dict[str, list[ConhecimentoEmpresa]] = {}
    for item, origem, quando in itens:
        existentes = cache.get(item.categoria)
        if existentes is None:
            existentes = list(
                (
                    await sessao.scalars(
                        select(ConhecimentoEmpresa).where(
                            ConhecimentoEmpresa.usuario_id == usuario_id,
                            ConhecimentoEmpresa.categoria == item.categoria,
                        )
                    )
                ).all()
            )
            cache[item.categoria] = existentes
        chave = chave_de(item.categoria, item.titulo)
        alvo = next((e for e in existentes if e.chave == chave), None)
        if alvo is None:
            pal = palavras(item.titulo)
            melhor = max(
                existentes, key=lambda e: semelhanca(pal, palavras(e.titulo)), default=None
            )
            if (
                melhor is not None
                and semelhanca(pal, palavras(melhor.titulo)) >= LIMITE_SEMELHANCA_TITULO
            ):
                alvo = melhor
        if alvo is None:
            novo = ConhecimentoEmpresa(
                usuario_id=usuario_id,
                categoria=item.categoria,
                chave=chave,
                titulo=item.titulo[:MAX_TITULO],
                conteudo=item.conteudo[:MAX_CONTEUDO],
                ocorrencias=1,
                origens=[origem],
                primeira_em=quando,
                ultima_em=quando,
                anteriores=[],
            )
            sessao.add(novo)
            await sessao.flush()
            existentes.append(novo)
            novos += 1
            continue
        if alvo.apagado_em is not None:
            continue
        alvo.ocorrencias += 1
        alvo.origens = [*alvo.origens, origem][-MAX_ORIGENS:]
        igual = mesmo_conteudo(alvo.conteudo, item.conteudo)
        if not igual and not alvo.travado:
            alvo.contraditorio = True
            if quando >= alvo.ultima_em:
                alvo.anteriores = [
                    *alvo.anteriores,
                    {"conteudo": alvo.conteudo, "em": _agora_iso(alvo.ultima_em)},
                ][-MAX_ANTERIORES:]
                alvo.conteudo = item.conteudo[:MAX_CONTEUDO]
            else:
                alvo.anteriores = [
                    *alvo.anteriores,
                    {"conteudo": item.conteudo[:MAX_CONTEUDO], "em": _agora_iso(quando)},
                ][-MAX_ANTERIORES:]
        if quando > alvo.ultima_em:
            alvo.ultima_em = quando
        alvo.atualizado_em = datetime.now(UTC)
        atualizados += 1
    await sessao.flush()
    return novos, atualizados


async def buscar(
    sessao: AsyncSession,
    usuario_id: UUID,
    consulta: str,
    *,
    categoria: str | None = None,
    limite: int = 5,
) -> list[ConhecimentoEmpresa]:
    """Busca por palavras (sem acento). Só itens do usuário e não apagados; empate: o mais
    repetido e depois o mais recente."""
    termos = palavras(consulta)
    if not termos:
        return []
    consulta_sql = select(ConhecimentoEmpresa).where(
        ConhecimentoEmpresa.usuario_id == usuario_id, ConhecimentoEmpresa.apagado_em.is_(None)
    )
    if categoria:
        consulta_sql = consulta_sql.where(ConhecimentoEmpresa.categoria == categoria)
    pontuados: list[tuple[float, ConhecimentoEmpresa]] = []
    for item in (await sessao.scalars(consulta_sql.limit(5_000))).all():
        no_titulo = termos & palavras(item.titulo)
        no_conteudo = termos & palavras(item.conteudo)
        ponto = 2 * len(no_titulo) + len(no_conteudo - no_titulo)
        if ponto:
            pontuados.append((ponto + math.log1p(item.ocorrencias) / 10, item))
    pontuados.sort(key=lambda par: (par[0], par[1].ultima_em), reverse=True)
    return [item for _, item in pontuados[:limite]]


def texto_do_item(item: ConhecimentoEmpresa) -> str:
    marca = " (há versões contraditórias; vale a mais recente)" if item.contraditorio else ""
    return f"[{item.categoria}] {item.titulo}: {item.conteudo} (visto {item.ocorrencias}x){marca}"
