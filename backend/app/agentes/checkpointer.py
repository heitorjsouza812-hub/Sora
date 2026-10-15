"""Checkpointer dos agentes (especificação §6.1, "Como uma etapa roda" e
"Pausas e retomada").

``AsyncPostgresSaver`` (``langgraph-checkpoint-postgres``, driver ``psycopg``
3) no mesmo PostgreSQL, em tabelas próprias criadas pelo ``setup()``. Cada
etapa roda com ``thread_id = "etapa:{etapa_id}"``.

A URL é sempre convertida por ``app.core.config.url_psycopg``: a
``DATABASE_URL`` do SQLAlchemy vem como ``postgresql+asyncpg://``, que o
psycopg não entende.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import url_psycopg

TAMANHO_DO_POOL = 10

OPCOES_DE_CONEXAO: dict[str, Any] = {
    "autocommit": True,  # o saver controla as próprias transações
    "prepare_threshold": 0,  # sem prepared statements (funciona atrás de pgbouncer)
    "row_factory": dict_row,  # o saver lê as linhas como dicionário
}
"""Opções que o ``AsyncPostgresSaver`` exige em cada conexão do pool."""


def thread_da_etapa(etapa_id: UUID) -> str:
    """``"etapa:{etapa_id}"``."""
    return f"etapa:{etapa_id}"


def thread_da_conversa(conversa_id: UUID) -> str:
    """Thread da Sora ou de um agente individual numa conversa: ``"conversa:{id}"``."""
    return f"conversa:{conversa_id}"


async def abrir_checkpointer(
    database_url: str, *, tamanho_do_pool: int = TAMANHO_DO_POOL
) -> AsyncPostgresSaver:
    """Abre o checkpointer (uma vez por worker) e roda o ``setup()``.

    Aceita a ``DATABASE_URL`` crua ou já convertida; sempre usa a do psycopg.
    """
    pool: AsyncConnectionPool[Any] = AsyncConnectionPool(
        url_psycopg(database_url),
        min_size=1,
        max_size=tamanho_do_pool,
        kwargs=OPCOES_DE_CONEXAO,
        open=False,
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await saver.setup()
    except BaseException:
        await pool.close()
        raise
    return saver


async def fechar_checkpointer(checkpointer: AsyncPostgresSaver) -> None:
    """Fecha o pool do checkpointer no desligamento do worker."""
    await checkpointer.conn.close()  # o pool aberto em ``abrir_checkpointer``
