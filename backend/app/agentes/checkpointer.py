"""Checkpointer dos agentes (especificação §6.1, "Como uma etapa roda" e
"Pausas e retomada").

``AsyncPostgresSaver`` (``langgraph-checkpoint-postgres``, driver ``psycopg``
3) no mesmo PostgreSQL, em tabelas próprias criadas pelo ``setup()``. Cada
etapa roda com ``thread_id = "etapa:{etapa_id}"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


def thread_da_etapa(etapa_id: UUID) -> str:
    """``"etapa:{etapa_id}"``."""
    raise NotImplementedError


def thread_da_conversa(conversa_id: UUID) -> str:
    """Thread da Sora ou de um agente individual numa conversa."""
    raise NotImplementedError


async def abrir_checkpointer(database_url: str) -> AsyncPostgresSaver:
    """Abre o checkpointer (uma vez por worker) e roda o ``setup()``."""
    raise NotImplementedError


async def fechar_checkpointer(checkpointer: AsyncPostgresSaver) -> None:
    """Fecha o pool do checkpointer no desligamento do worker."""
    raise NotImplementedError
