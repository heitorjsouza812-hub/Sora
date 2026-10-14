"""Leitura segura de páginas (especificação §8.1, "Como ler páginas").

Download com ``httpx`` (prazo de 10 s, até 5 redirecionamentos e 5 MB),
bloqueio de endereços internos antes do download e em cada redirecionamento,
extração com ``trafilatura`` (PDF com ``pypdf``) e cache de 24 h no Redis.
"""

from __future__ import annotations

import ipaddress

from pydantic import BaseModel

PRAZO_SEGUNDOS = 10
MAX_REDIRECIONAMENTOS = 5
MAX_BYTES = 5 * 1024 * 1024

REDES_BLOQUEADAS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)
"""Faixas privadas e locais recusadas (lista inicial; a lógica também confere
``is_private``, ``is_loopback``, ``is_link_local`` e IPv4 mapeado em IPv6)."""


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


async def validar_destino(url: str) -> None:
    """Resolve o domínio e recusa IPs privados ou locais. Levanta ``EnderecoBloqueado``."""
    raise NotImplementedError


async def ler_pagina(url: str) -> PaginaLida:
    """Baixa a página com as travas acima e extrai o texto principal."""
    raise NotImplementedError


def extrair_texto(conteudo: bytes, tipo: str, url: str) -> tuple[str | None, str]:
    """Extrai ``(titulo, texto)`` de HTML (``trafilatura``) ou PDF (``pypdf``)."""
    raise NotImplementedError
