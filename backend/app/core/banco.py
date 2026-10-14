"""Motor e sessões assíncronas do PostgreSQL; especificação §§1 e 8.4."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import obter_configuracao


def criar_motor(url: str) -> AsyncEngine:
    """Cria o motor assíncrono SQLAlchemy 2 para a URL informada."""
    return create_async_engine(url, pool_pre_ping=True)


@lru_cache
def fabrica_sessoes() -> async_sessionmaker[AsyncSession]:
    """Fábrica única de sessões, ligada ao banco da configuração."""
    motor = criar_motor(obter_configuracao().database_url)
    return async_sessionmaker(motor, expire_on_commit=False)


async def obter_sessao() -> AsyncIterator[AsyncSession]:
    """Fornece uma sessão por requisição; confirma ao final e desfaz em caso de erro."""
    async with fabrica_sessoes()() as sessao:
        try:
            yield sessao
            await sessao.commit()
        except BaseException:
            await sessao.rollback()
            raise
