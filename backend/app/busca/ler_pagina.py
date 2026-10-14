"""Leitura segura de páginas (especificação §8.1, "Como ler páginas").

Download com ``httpx`` (prazo de 10 s, até 5 redirecionamentos e 5 MB),
bloqueio de endereços internos antes do download e em cada redirecionamento,
extração com ``trafilatura`` (PDF com ``pypdf``) e cache de 24 h no Redis.

Duas travas contra SSRF:

1. ``validar_destino`` resolve o domínio de cada URL (a inicial e cada
   ``Location``) e recusa se **qualquer** IP for interno.
2. ``BackendSeguro`` é a camada de rede do httpx: resolve de novo na hora de
   conectar, confere e conecta **no IP conferido**. Isso fecha o DNS rebinding
   (o domínio responder um IP público na checagem e um interno na conexão).
   O TLS continua usando o nome original (SNI e certificado).
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable
from io import BytesIO
from typing import TYPE_CHECKING, Any

import httpcore
import httpx
from pydantic import BaseModel

if TYPE_CHECKING:
    from redis.asyncio import Redis

PRAZO_SEGUNDOS = 10
MAX_REDIRECIONAMENTOS = 5
MAX_BYTES = 5 * 1024 * 1024
CACHE_SEGUNDOS = 24 * 60 * 60
AGENTE_USUARIO = "SoraBot/0.1 (+https://github.com/heitorjsouza812-hub/Sora)"

IP = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolvedor = Callable[[str, int], Awaitable[list[str]]]

REDES_BLOQUEADAS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT; metadados da Alibaba (100.100.100.200)
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local; metadados de nuvem (169.254.169.254)
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # ULA; metadados da AWS em IPv6 (fd00:ec2::254)
    ipaddress.ip_network("fe80::/10"),
)
"""Faixas recusadas sempre. Além delas, ``ip_bloqueado`` recusa tudo que não é
``is_global`` (reservado, documentação, benchmark…) e multicast."""

NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))

TIPOS_HTML = {"text/html", "application/xhtml+xml"}
TIPOS_TEXTO = {"text/plain", "text/markdown", "text/csv"}
TIPO_PDF = "application/pdf"


class PaginaLida(BaseModel):
    url: str
    url_final: str
    titulo: str | None = None
    texto: str
    tipo: str


class EnderecoBloqueado(Exception):
    """A URL (ou um redirecionamento) aponta para um endereço interno."""


class ErroLeitura(Exception):
    """Prazo, tamanho, tipo não suportado ou falha de rede."""


# ---------- endereços ----------


def ip_bloqueado(ip: IP) -> bool:
    """O IP é interno, local, reservado ou esconde um IPv4 interno."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip_bloqueado(ip.ipv4_mapped)
        if ip.sixtofour is not None:
            return ip_bloqueado(ip.sixtofour)
        if ip.teredo is not None:
            return True
        if any(ip in rede for rede in NAT64):
            return ip_bloqueado(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    if any(ip in rede for rede in REDES_BLOQUEADAS):
        return True
    return ip.is_multicast or ip.is_unspecified or ip.is_reserved or not ip.is_global


def _ip_literal(host: str) -> IP | None:
    try:
        return ipaddress.ip_address(host.strip("[]").split("%", 1)[0])
    except ValueError:
        return None


async def resolver_dns(host: str, porta: int) -> list[str]:
    """Todos os IPs do domínio, sem repetir."""
    laco = asyncio.get_running_loop()
    try:
        infos = await laco.getaddrinfo(host, porta, type=socket.SOCK_STREAM)
    except socket.gaierror as erro:
        raise ErroLeitura(f"Não encontrei o endereço {host}.") from erro
    ips: list[str] = []
    for *_, endereco in infos:
        ip = str(endereco[0]).split("%", 1)[0]
        if ip not in ips:
            ips.append(ip)
    return ips


async def ips_permitidos(host: str, porta: int, resolver: Resolvedor = resolver_dns) -> list[str]:
    """Resolve e confere o host. Levanta ``EnderecoBloqueado`` se algum IP for interno."""
    literal = _ip_literal(host)
    if literal is not None:
        if ip_bloqueado(literal):
            raise EnderecoBloqueado(f"Endereço interno bloqueado: {host}")
        return [str(literal)]
    ips = await resolver(host, porta)
    if not ips:
        raise ErroLeitura(f"Não encontrei o endereço {host}.")
    for bruto in ips:
        ip = _ip_literal(bruto)
        if ip is None or ip_bloqueado(ip):
            raise EnderecoBloqueado(f"{host} aponta para um endereço interno.")
    return ips


def validar_url(url: str | httpx.URL) -> httpx.URL:
    """Só ``http``/``https``, com host e sem usuário e senha na URL."""
    try:
        alvo = httpx.URL(url)
    except (httpx.InvalidURL, TypeError) as erro:
        raise ErroLeitura("URL inválida.") from erro
    if alvo.scheme not in {"http", "https"}:
        raise EnderecoBloqueado("Só leio páginas http e https.")
    if not alvo.host:
        raise ErroLeitura("URL sem domínio.")
    if alvo.userinfo:
        raise EnderecoBloqueado("URL com usuário e senha não é aceita.")
    return alvo


async def validar_destino(url: str | httpx.URL, resolver: Resolvedor = resolver_dns) -> None:
    """Resolve o domínio e recusa IPs privados ou locais. Levanta ``EnderecoBloqueado``."""
    alvo = validar_url(url)
    porta = alvo.port or (443 if alvo.scheme == "https" else 80)
    await ips_permitidos(alvo.host, porta, resolver)


class BackendSeguro(httpcore.AsyncNetworkBackend):
    """Camada de rede que só conecta em IP público, no IP que ela mesma conferiu."""

    def __init__(
        self,
        resolver: Resolvedor = resolver_dns,
        interno: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._resolver = resolver
        self._interno = interno or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 (assinatura do httpcore)
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        ips = await ips_permitidos(host, port, self._resolver)
        return await self._interno.connect_tcp(
            ips[0],
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 (assinatura do httpcore)
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise EnderecoBloqueado("Socket local bloqueado.")

    async def sleep(self, seconds: float) -> None:
        await self._interno.sleep(seconds)


def criar_cliente(resolver: Resolvedor = resolver_dns) -> httpx.AsyncClient:
    """Cliente httpx da leitura: sem proxy do ambiente, sem seguir redirecionamento
    sozinho (cada ``Location`` é conferido aqui) e com o ``BackendSeguro``."""
    transporte = httpx.AsyncHTTPTransport(retries=0)
    # O httpx não expõe a camada de rede; trocamos a do pool antes da primeira conexão.
    transporte._pool._network_backend = BackendSeguro(resolver)
    return httpx.AsyncClient(
        transport=transporte,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(PRAZO_SEGUNDOS),
        headers={"User-Agent": AGENTE_USUARIO, "Accept": "text/html,application/pdf,*/*;q=0.5"},
    )


# ---------- download ----------


def _tipo(resposta: httpx.Response) -> str:
    return resposta.headers.get("content-type", "").split(";", 1)[0].strip().lower()


async def _baixar(
    cliente: httpx.AsyncClient, url: str, resolver: Resolvedor
) -> tuple[httpx.URL, str, bytes]:
    """Segue até 5 redirecionamentos, conferindo cada destino, e baixa até 5 MB."""
    atual = validar_url(url)
    for _ in range(MAX_REDIRECIONAMENTOS + 1):
        await validar_destino(atual, resolver)
        async with cliente.stream("GET", atual) as resposta:
            if resposta.is_redirect:
                destino = resposta.headers.get("location")
                if not destino:
                    raise ErroLeitura("Redirecionamento sem destino.")
                atual = validar_url(atual.join(destino))
                continue
            if resposta.status_code >= 400:
                raise ErroLeitura(f"A página respondeu {resposta.status_code}.")
            tamanho = resposta.headers.get("content-length")
            if tamanho and tamanho.isdigit() and int(tamanho) > MAX_BYTES:
                raise ErroLeitura("Página maior que 5 MB.")
            corpo = bytearray()
            async for pedaco in resposta.aiter_bytes():
                corpo.extend(pedaco)
                if len(corpo) > MAX_BYTES:
                    raise ErroLeitura("Página maior que 5 MB.")
            return atual, _tipo(resposta), bytes(corpo)
    raise ErroLeitura("Redirecionamentos demais.")


def chave_cache(url: str) -> str:
    return "pagina:" + hashlib.sha256(url.encode()).hexdigest()


async def ler_pagina(
    url: str,
    *,
    redis: Redis | None = None,
    cliente: httpx.AsyncClient | None = None,
    resolver: Resolvedor = resolver_dns,
) -> PaginaLida:
    """Baixa a página com as travas acima e extrai o texto principal.

    ``cliente`` é para os testes (``httpx.MockTransport``); em produção o
    cliente é o de ``criar_cliente``.
    """
    validar_url(url)
    if redis is not None and (guardada := await redis.get(chave_cache(url))):
        return PaginaLida.model_validate_json(guardada)

    proprio = cliente is None
    cliente = cliente or criar_cliente(resolver)
    try:
        async with asyncio.timeout(PRAZO_SEGUNDOS):
            final, tipo, corpo = await _baixar(cliente, url, resolver)
    except TimeoutError as erro:
        raise ErroLeitura("A página demorou mais de 10 segundos.") from erro
    except httpx.HTTPError as erro:
        raise ErroLeitura(f"Não consegui abrir a página ({type(erro).__name__}).") from erro
    finally:
        if proprio:
            await cliente.aclose()

    titulo, texto = extrair_texto(corpo, tipo, str(final))
    pagina = PaginaLida(url=url, url_final=str(final), titulo=titulo, texto=texto, tipo=tipo)
    if redis is not None:
        await redis.set(chave_cache(url), pagina.model_dump_json(), ex=CACHE_SEGUNDOS)
    return pagina


# ---------- extração ----------


def _extrair_html(conteudo: bytes, url: str) -> tuple[str | None, str]:
    import trafilatura

    documento = trafilatura.bare_extraction(conteudo, url=url, with_metadata=True)
    titulo = getattr(documento, "title", None) if documento is not None else None
    texto = (getattr(documento, "text", None) or "") if documento is not None else ""
    return titulo or None, texto.strip()


def _extrair_pdf(conteudo: bytes) -> tuple[str | None, str]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        leitor = PdfReader(BytesIO(conteudo))
        paginas = [(pagina.extract_text() or "").strip() for pagina in leitor.pages]
        titulo = leitor.metadata.title if leitor.metadata else None
    except (PdfReadError, ValueError, KeyError) as erro:
        raise ErroLeitura("Não consegui ler o PDF.") from erro
    return titulo or None, "\n\n".join(p for p in paginas if p)


def extrair_texto(conteudo: bytes, tipo: str, url: str) -> tuple[str | None, str]:
    """Extrai ``(titulo, texto)`` de HTML (``trafilatura``), PDF (``pypdf``) ou texto puro."""
    if tipo in TIPOS_HTML or (not tipo and conteudo.lstrip()[:15].lower().startswith(b"<!doctype")):
        titulo, texto = _extrair_html(conteudo, url)
    elif tipo == TIPO_PDF or conteudo.startswith(b"%PDF-"):
        titulo, texto = _extrair_pdf(conteudo)
    elif tipo in TIPOS_TEXTO:
        titulo, texto = None, conteudo.decode("utf-8", errors="replace").strip()
    else:
        raise ErroLeitura(f"Não leio arquivos do tipo {tipo or 'desconhecido'}.")
    if not texto:
        raise ErroLeitura("Não encontrei texto nessa página.")
    return titulo, texto
