"""Acesso à infraestrutura (banco, Redis, volume de arquivos) para as ferramentas.

O ``ContextoFerramenta`` leva só ids (quem chama), nunca conexões. O Redis é o mesmo
de ``app.ferramentas.ambiente`` (um por processo, o dos eventos). Cada chamada de
ferramenta abre a própria sessão e confirma ao final.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.ferramentas import ambiente


def obter_redis() -> Redis:
    return ambiente.redis_dos_eventos()


@asynccontextmanager
async def abrir_sessao() -> AsyncIterator[AsyncSession]:
    """Sessão própria da chamada: confirma se tudo deu certo, desfaz se falhou."""
    from app.core.banco import fabrica_sessoes

    async with fabrica_sessoes()() as sessao:
        try:
            yield sessao
            await sessao.commit()
        except BaseException:
            await sessao.rollback()
            raise


def raiz_dos_arquivos() -> Path:
    """Volume dos anexos (``PASTA_ARQUIVOS``)."""
    from app.core.config import obter_configuracao

    return obter_configuracao().pasta_arquivos
