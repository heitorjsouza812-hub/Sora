"""Define os contratos assíncronos do PostgreSQL; especificação §§1 e 8.4."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


def criar_motor(url: str) -> AsyncEngine:
    """Cria o motor assíncrono SQLAlchemy 2 para a URL informada."""
    raise NotImplementedError


async def obter_sessao() -> AsyncIterator[AsyncSession]:
    """Fornece uma sessão transacional assíncrona por requisição."""
    raise NotImplementedError
    yield  # pragma: no cover
