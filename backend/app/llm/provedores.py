"""Provedores do usuário: tipos, configuração por chamada e teste da chave.

Especificação: §5 "Como o usuário conecta uma API" e §1 (tabela ``provedores``).

Quem chama este módulo (a rota ``POST /v1/provedores``, o worker) decifra a chave na hora e
entrega um ``ConfigProvedor``. A chave fica em ``SecretStr`` para nunca vazar em log, evento ou
``repr``. Este módulo não conhece o banco nem a cifra, e nenhuma mensagem de erro carrega a chave.

``base_url`` vem do usuário, então é tratado como destino não confiável (API-02, SSRF):

- tipos com URL oficial (Groq, OpenAI, Anthropic, Google, OpenRouter) **ignoram** ``base_url``;
- ``validar_base_url``: só http/https, sem usuário e senha, até 2048 caracteres, https em
  produção, e nada de localhost/IP interno sem ``PERMITIR_PROVEDOR_REDE_LOCAL``;
- o teste da chave usa o ``transporte_seguro`` de ``app.busca.ler_pagina`` (confere o IP na
  hora de conectar, sem proxy do ambiente, sem seguir redirecionamento);
- as chamadas do LiteLLM passam por ``ClienteLiteLLMProtegido``, que resolve o domínio do
  ``api_base`` e recusa IP interno antes de cada chamada.
"""

from __future__ import annotations

import asyncio
import socket
import weakref
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpcore
import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from app.busca.ler_pagina import (
    EnderecoBloqueado,
    ErroLeitura,
    Resolvedor,
    ip_bloqueado,
    ips_permitidos,
    resolver_dns,
    transporte_seguro,
)
from app.busca.ler_pagina import _ip_literal as ip_literal
from app.modelos.enumeracoes import TipoProvedor

# Prefixo do nome do modelo no LiteLLM para cada tipo (§5, catálogo). A API compatível com a da
# OpenAI usa ``openai/<modelo>`` junto com ``api_base``.
PREFIXO_LITELLM: dict[TipoProvedor, str] = {
    TipoProvedor.GROQ: "groq",
    TipoProvedor.OPENAI: "openai",
    TipoProvedor.ANTHROPIC: "anthropic",
    TipoProvedor.GOOGLE: "gemini",
    TipoProvedor.OPENROUTER: "openrouter",
    TipoProvedor.COMPATIVEL_OPENAI: "openai",
    TipoProvedor.OLLAMA: "ollama",
}

URL_OLLAMA_PADRAO = "http://localhost:11434"
"""Endereço padrão do Ollama quando o usuário não informa ``base_url``."""

# Onde listar os modelos de cada provedor (teste da chave, §5 passo 2).
_URL_LISTAGEM: dict[TipoProvedor, str] = {
    TipoProvedor.GROQ: "https://api.groq.com/openai/v1",
    TipoProvedor.OPENAI: "https://api.openai.com/v1",
    TipoProvedor.OPENROUTER: "https://openrouter.ai/api/v1",
    TipoProvedor.ANTHROPIC: "https://api.anthropic.com/v1",
    TipoProvedor.GOOGLE: "https://generativelanguage.googleapis.com/v1beta",
}

TIPOS_COM_URL_OFICIAL = frozenset(_URL_LISTAGEM)
"""Tipos cujo endereço é fixo: o ``base_url`` informado pelo usuário é ignorado."""

BASE_URL_MAX = 2048

_VERSAO_API_ANTHROPIC = "2023-06-01"
_PRAZO_LISTAGEM_S = 15.0
_CHAVE_SEM_CHAVE = "sem-chave"
"""O LiteLLM exige alguma chave em ``openai/``; servidores compatíveis sem autenticação recebem
este valor fixo."""


class ErroProvedor(Exception):
    """Falha ao falar com um provedor. Nunca carrega a chave na mensagem."""


class ChaveInvalida(ErroProvedor):
    """O provedor recusou a chave (teste de conexão ou chamada)."""


class ConfigProvedor(BaseModel):
    """Tudo que o LiteLLM precisa para falar com o provedor do usuário numa chamada."""

    model_config = ConfigDict(frozen=True)

    provedor_id: UUID | None = None
    tipo: TipoProvedor
    api_key: SecretStr | None = None  # None no Ollama local sem chave
    base_url: str | None = None  # obrigatória para compativel_openai e ollama


class DestinoBloqueado(ErroProvedor):
    """A URL do provedor aponta para a rede interna ou não segue as regras de ``base_url``."""


@dataclass(frozen=True, slots=True)
class PoliticaRede:
    """O que a configuração permite para a URL de uma API de modelos."""

    producao: bool
    rede_local: bool


def politica_de_rede() -> PoliticaRede:
    """Lê ``AMBIENTE`` e ``PERMITIR_PROVEDOR_REDE_LOCAL`` da configuração."""
    from app.core.config import obter_configuracao

    config = obter_configuracao()
    return PoliticaRede(producao=config.producao, rede_local=config.rede_local_permitida)


ResolvedorSincrono = Callable[[str, int], list[str]]


def resolver_sincrono(host: str, porta: int) -> list[str]:
    """Todos os IPs do domínio (``getaddrinfo``). Levanta ``DestinoBloqueado`` se não resolver."""
    try:
        infos = socket.getaddrinfo(host, porta, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as erro:
        raise DestinoBloqueado(f"Não encontrei o endereço {host}.") from erro
    return [str(info[4][0]).split("%", 1)[0] for info in infos]


def _host_local(host: str, porta: int, resolver: ResolvedorSincrono) -> bool:
    """O host é ``localhost`` ou **algum** IP dele (literal ou resolvido) é interno.

    Pega ``0x7f.1``, ``localtest.me``, ``redis`` (nome do serviço no compose) etc.
    """
    nome = host.strip("[]").rstrip(".").lower()
    if nome == "localhost" or nome.endswith(".localhost"):
        return True
    literal = ip_literal(nome)
    if literal is not None:
        return ip_bloqueado(literal)
    for bruto in resolver(nome, porta):
        ip = ip_literal(bruto)
        if ip is None or ip_bloqueado(ip):
            return True
    return False


def validar_base_url(
    tipo: TipoProvedor,
    base_url: str | None,
    politica: PoliticaRede,
    resolver: ResolvedorSincrono | None = None,
) -> str | None:
    """Devolve o ``base_url`` limpo (sem barra final), ``None`` se não houver ou se o tipo tem
    URL oficial; levanta ``DestinoBloqueado`` se a URL não for aceitável.

    Fora da rede local permitida, resolve o domínio e recusa se algum IP for interno. A
    conferência de verdade é na hora de conectar (``transporte_seguro``); esta só dá o erro cedo.
    """
    if tipo in TIPOS_COM_URL_OFICIAL or base_url is None:
        return None
    limpa = base_url.strip().rstrip("/")
    if not limpa:
        return None
    if len(limpa) > BASE_URL_MAX:
        raise DestinoBloqueado(f"A URL da API pode ter até {BASE_URL_MAX} caracteres.")
    try:
        url = httpx.URL(limpa)
    except (httpx.InvalidURL, TypeError) as erro:
        raise DestinoBloqueado("URL da API inválida.") from erro
    if url.scheme not in {"http", "https"} or not url.host:
        raise DestinoBloqueado("A URL da API precisa começar com https://.")
    if url.userinfo:
        raise DestinoBloqueado("Não coloque usuário e senha na URL; use o campo da chave.")
    if politica.rede_local:
        return limpa
    if politica.producao and url.scheme != "https":
        raise DestinoBloqueado("A URL da API precisa usar https.")
    porta = url.port or (443 if url.scheme == "https" else 80)
    if _host_local(url.host, porta, resolver or resolver_sincrono):
        raise DestinoBloqueado("A URL da API aponta para a rede local, o que não é permitido.")
    return limpa


def _base(config: ConfigProvedor, politica: PoliticaRede | None) -> str | None:
    return validar_base_url(config.tipo, config.base_url, politica or politica_de_rede())


def _url_ollama(base: str | None, politica: PoliticaRede | None) -> str:
    if base is not None:
        return base
    if not (politica or politica_de_rede()).rede_local:
        raise DestinoBloqueado(
            "Informe a URL https do seu Ollama (o endereço local não é permitido neste servidor)."
        )
    return URL_OLLAMA_PADRAO


def _chave_em_texto(config: ConfigProvedor) -> str | None:
    if config.api_key is None:
        return None
    chave = config.api_key.get_secret_value().strip()
    return chave or None


def parametros_litellm(
    config: ConfigProvedor, politica: PoliticaRede | None = None
) -> dict[str, Any]:
    """Devolve ``api_key`` e ``api_base`` no formato que o LiteLLM/ChatLiteLLM espera.

    Só entram as chaves que têm valor. Levanta ``ErroProvedor`` se faltar a URL de uma API
    compatível com a da OpenAI e ``DestinoBloqueado`` se a URL não for aceitável.
    """
    base = _base(config, politica)
    chave = _chave_em_texto(config)

    if config.tipo is TipoProvedor.OLLAMA:
        return {"api_base": _url_ollama(base, politica)}
    if config.tipo is TipoProvedor.COMPATIVEL_OPENAI:
        if base is None:
            raise ErroProvedor("Informe a URL da API compatível com a da OpenAI.")
        return {"api_base": base, "api_key": chave or _CHAVE_SEM_CHAVE}

    parametros: dict[str, Any] = {}
    if chave is not None:
        parametros["api_key"] = chave
    if base is not None:
        parametros["api_base"] = base
    return parametros


def _requisicao_de_listagem(
    config: ConfigProvedor, politica: PoliticaRede | None = None
) -> tuple[str, dict[str, str]]:
    """URL e cabeçalhos da listagem de modelos do provedor."""
    base = _base(config, politica)
    chave = _chave_em_texto(config) or ""
    tipo = config.tipo

    if tipo is TipoProvedor.OLLAMA:
        return f"{_url_ollama(base, politica)}/api/tags", {}
    if tipo is TipoProvedor.ANTHROPIC:
        return (
            f"{base or _URL_LISTAGEM[tipo]}/models?limit=1000",
            {"x-api-key": chave, "anthropic-version": _VERSAO_API_ANTHROPIC},
        )
    if tipo is TipoProvedor.GOOGLE:
        return f"{base or _URL_LISTAGEM[tipo]}/models?pageSize=1000", {"x-goog-api-key": chave}
    if tipo is TipoProvedor.COMPATIVEL_OPENAI:
        if base is None:
            raise ErroProvedor("Informe a URL da API compatível com a da OpenAI.")
        cabecalhos = {"Authorization": f"Bearer {chave}"} if chave else {}
        return f"{base}/models", cabecalhos
    return f"{base or _URL_LISTAGEM[tipo]}/models", {"Authorization": f"Bearer {chave}"}


def _nomes_dos_modelos(config: ConfigProvedor, corpo: Any) -> list[str]:
    """Extrai os ids da resposta e devolve no formato do LiteLLM (``prefixo/id``)."""
    if not isinstance(corpo, dict):
        raise ErroProvedor("O provedor devolveu uma resposta que a Sora não entende.")
    prefixo = PREFIXO_LITELLM[config.tipo]

    if config.tipo is TipoProvedor.OLLAMA:
        itens = [m.get("name") for m in corpo.get("models", []) if isinstance(m, dict)]
    elif config.tipo is TipoProvedor.GOOGLE:
        itens = [
            str(m.get("name", "")).removeprefix("models/")
            for m in corpo.get("models", [])
            if isinstance(m, dict)
        ]
    else:
        itens = [m.get("id") for m in corpo.get("data", []) if isinstance(m, dict)]

    nomes = {f"{prefixo}/{item}" for item in itens if isinstance(item, str) and item}
    return sorted(nomes)


def criar_cliente_listagem(
    politica: PoliticaRede, resolver: Resolvedor = resolver_dns
) -> httpx.AsyncClient:
    """Cliente do teste da chave: sem proxy do ambiente, sem seguir redirecionamento e, fora da
    rede local permitida, só conectando em IP público (``transporte_seguro``)."""
    return httpx.AsyncClient(
        timeout=_PRAZO_LISTAGEM_S,
        trust_env=False,
        follow_redirects=False,
        transport=None if politica.rede_local else transporte_seguro(resolver),
    )


async def listar_modelos(
    config: ConfigProvedor,
    *,
    cliente: httpx.AsyncClient | None = None,
    politica: PoliticaRede | None = None,
) -> list[str]:
    """Testa a chave listando os modelos do provedor (nomes no formato do LiteLLM).

    Levanta ``ChaveInvalida`` se o provedor recusar; a rota devolve 422 e não salva nada.
    ``DestinoBloqueado`` se a URL apontar para a rede interna. ``cliente`` existe para os
    testes injetarem um transporte falso (sem rede).
    """
    politica = politica or politica_de_rede()
    url, cabecalhos = _requisicao_de_listagem(config, politica)
    proprio = cliente is None
    http = cliente or criar_cliente_listagem(politica)
    try:
        try:
            resposta = await http.get(url, headers=cabecalhos)
        except EnderecoBloqueado as erro:
            raise DestinoBloqueado("A URL da API aponta para um endereço interno.") from erro
        except httpx.TimeoutException as erro:
            raise ErroProvedor("O provedor demorou demais para responder.") from erro
        except httpx.HTTPError as erro:
            raise ErroProvedor("Não foi possível conectar ao provedor.") from erro
    finally:
        if proprio:
            await http.aclose()

    status = resposta.status_code
    recusas = {400, 401, 403} if config.tipo is TipoProvedor.GOOGLE else {401, 403}
    if status in recusas:
        raise ChaveInvalida("O provedor recusou a chave.")
    if status >= 400:
        raise ErroProvedor(f"O provedor respondeu com erro {status}.")
    try:
        corpo = resposta.json()
    except ValueError as erro:
        raise ErroProvedor("O provedor devolveu uma resposta que a Sora não entende.") from erro
    return _nomes_dos_modelos(config, corpo)


# ---------------------------------------------------------------- chamadas do LiteLLM (API-02)

PRAZO_CHAMADA_S = 600.0

_CLIENTES_POR_LACO: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = (
    weakref.WeakKeyDictionary()
)
"""Um ``httpx.AsyncClient`` seguro por laço de eventos (o pool do httpx é preso ao laço)."""


def cliente_http_seguro(resolver: Resolvedor = resolver_dns) -> httpx.AsyncClient:
    """Cliente httpx das chamadas de modelo em URL do usuário: conecta só em IP público,
    conferido na hora da conexão (anti DNS rebinding), não segue redirecionamento e ignora
    proxy do ambiente. Compartilhado no laço atual quando usa o resolvedor padrão."""

    def novo() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=transporte_seguro(resolver),
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(PRAZO_CHAMADA_S, connect=10.0),
        )

    if resolver is not resolver_dns:
        return novo()
    laco = asyncio.get_running_loop()
    cliente = _CLIENTES_POR_LACO.get(laco)
    if cliente is None or cliente.is_closed:
        cliente = _CLIENTES_POR_LACO[laco] = novo()
    return cliente


def ips_permitidos_sincrono(
    host: str, porta: int, resolver: ResolvedorSincrono = resolver_sincrono
) -> list[str]:
    """Versão síncrona de ``ips_permitidos``: resolve e recusa se **algum** IP for interno."""
    literal = ip_literal(host)
    if literal is not None:
        if ip_bloqueado(literal):
            raise EnderecoBloqueado(f"Endereço interno bloqueado: {host}")
        return [str(literal)]
    try:
        ips = resolver(host, porta)
    except DestinoBloqueado as erro:
        raise ErroLeitura(f"Não encontrei o endereço {host}.") from erro
    if not ips:
        raise ErroLeitura(f"Não encontrei o endereço {host}.")
    for bruto in ips:
        ip = ip_literal(bruto)
        if ip is None or ip_bloqueado(ip):
            raise EnderecoBloqueado(f"{host} aponta para um endereço interno.")
    return ips


class BackendSeguroSincrono(httpcore.NetworkBackend):
    """Par síncrono do ``BackendSeguro`` (``ler_pagina``): resolve e confere o IP **na hora de
    conectar** e conecta nesse IP (anti DNS rebinding). O TLS segue validando o nome original."""

    def __init__(
        self,
        resolver: ResolvedorSincrono = resolver_sincrono,
        interno: httpcore.NetworkBackend | None = None,
    ) -> None:
        self._resolver = resolver
        self._interno = interno or httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        ips = ips_permitidos_sincrono(host, port, self._resolver)
        return self._interno.connect_tcp(
            ips[0],
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        raise EnderecoBloqueado("Socket local bloqueado.")

    def sleep(self, seconds: float) -> None:
        self._interno.sleep(seconds)


def transporte_seguro_sincrono(
    resolver: ResolvedorSincrono = resolver_sincrono,
) -> httpx.HTTPTransport:
    """Transporte httpx síncrono que só conecta em IP público (``BackendSeguroSincrono``)."""
    transporte = httpx.HTTPTransport(retries=0)
    # O httpx não expõe a camada de rede; trocamos a do pool antes da primeira conexão.
    transporte._pool._network_backend = BackendSeguroSincrono(resolver)
    return transporte


def _destino(api_base: str) -> tuple[str, int]:
    url = httpx.URL(api_base)
    return url.host, url.port or (443 if url.scheme == "https" else 80)


def _prefixo(modelo: str) -> str:
    return modelo.split("/", 1)[0].lower() if "/" in modelo else ""


class ClienteLiteLLMProtegido:
    """Fica no lugar do módulo ``litellm`` dentro do ``ChatLiteLLM`` (campo ``client``).

    Para URL escolhida pelo usuário (``openai/`` compatível e ``ollama/``), cada chamada:

    1. confere o domínio do ``api_base`` (erro cedo e claro);
    2. vai pelo ``cliente_http_seguro``: o IP é conferido **de novo na conexão** (o DNS não
       pode trocar no meio) e redirecionamento **não** é seguido (um 307 para a rede interna
       vira erro, VAL-14). No ``openai/`` entra como ``http_client`` de um ``AsyncOpenAI``; no
       ``ollama/``, como ``AsyncHTTPHandler`` do LiteLLM.

    Outro provedor com ``api_base`` é recusado (falha fechada). A chamada síncrona tem as mesmas
    garantias, com o ``transporte_seguro_sincrono`` (``resolver_sinc``).
    """

    PREFIXOS = frozenset({"openai", "ollama", "ollama_chat"})

    def __init__(
        self,
        resolver: Resolvedor = resolver_dns,
        resolver_sinc: ResolvedorSincrono = resolver_sincrono,
    ) -> None:
        self._resolver = resolver
        self._resolver_sinc = resolver_sinc

    async def conferir(self, api_base: str | None) -> None:
        if not api_base:
            return
        host, porta = _destino(api_base)
        try:
            await ips_permitidos(host, porta, self._resolver)
        except (EnderecoBloqueado, ErroLeitura) as erro:
            raise DestinoBloqueado("A URL da API aponta para um endereço interno.") from erro

    def conferir_sincrono(self, api_base: str | None) -> None:
        if not api_base:
            return
        host, porta = _destino(api_base)
        try:
            ips_permitidos_sincrono(host, porta, self._resolver_sinc)
        except EnderecoBloqueado as erro:
            raise DestinoBloqueado("A URL da API aponta para um endereço interno.") from erro
        except ErroLeitura as erro:
            raise ErroProvedor("Não foi possível conectar ao provedor.") from erro

    def _exigir_suportado(self, kwargs: dict[str, Any]) -> str:
        prefixo = _prefixo(str(kwargs.get("model", "")))
        if prefixo not in self.PREFIXOS:
            raise DestinoBloqueado(
                "URL própria só é aceita em API compatível com a OpenAI e Ollama."
            )
        return prefixo

    def _cliente_assincrono(self, prefixo: str, kwargs: dict[str, Any]) -> Any:
        http = cliente_http_seguro(self._resolver)
        if prefixo == "openai":
            from openai import AsyncOpenAI

            return AsyncOpenAI(
                api_key=kwargs.get("api_key") or "sem-chave",
                base_url=kwargs["api_base"],
                http_client=http,
                max_retries=0,
            )
        from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler

        manipulador = AsyncHTTPHandler(follow_redirects=False)
        manipulador.client = http  # o LiteLLM usa este cliente e não o fecha
        return manipulador

    def _cliente_sincrono(self, prefixo: str, kwargs: dict[str, Any]) -> Any:
        http = httpx.Client(
            transport=transporte_seguro_sincrono(self._resolver_sinc),
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(PRAZO_CHAMADA_S, connect=10.0),
        )
        if prefixo == "openai":
            from openai import OpenAI

            return OpenAI(
                api_key=kwargs.get("api_key") or "sem-chave",
                base_url=kwargs["api_base"],
                http_client=http,
                max_retries=0,
            )
        from litellm.llms.custom_httpx.http_handler import HTTPHandler

        return HTTPHandler(client=http)

    def completion(self, **kwargs: Any) -> Any:
        import litellm

        if kwargs.get("api_base"):
            prefixo = self._exigir_suportado(kwargs)
            self.conferir_sincrono(kwargs["api_base"])
            kwargs["client"] = self._cliente_sincrono(prefixo, kwargs)
        return litellm.completion(**kwargs)

    async def acompletion(self, **kwargs: Any) -> Any:
        import litellm

        if kwargs.get("api_base"):
            prefixo = self._exigir_suportado(kwargs)
            await self.conferir(kwargs["api_base"])
            kwargs["client"] = self._cliente_assincrono(prefixo, kwargs)
        return await litellm.acompletion(**kwargs)

    def __getattr__(self, nome: str) -> Any:
        import litellm

        return getattr(litellm, nome)
