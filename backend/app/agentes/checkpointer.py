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


def thread_da_tarefa_canal(tarefa_id: UUID, turno_seq: int) -> str:
    """Thread de um turno de tarefa de grupo: cada turno começa limpo (o pacote do canal já traz
    o histórico) e a retomada de um cartão volta exatamente ao turno que pausou."""
    return f"canal-tarefa:{tarefa_id}:{turno_seq}"


def thread_da_conversa(conversa_id: UUID) -> str:
    """Thread da Sora ou de um agente individual numa conversa: ``"conversa:{id}"``."""
    return f"conversa:{conversa_id}"


async def pausa_da_conversa(
    sessao, saver, conversa_id: UUID, cartao: str
) -> tuple[str, str] | None:
    """Localiza o interrupt do cartão no checkpoint atual, inclusive de turnos anteriores."""
    from sqlalchemy import text

    base = thread_da_conversa(conversa_id)
    threads = await sessao.scalars(
        text(
            "SELECT DISTINCT w.thread_id FROM checkpoint_writes w "
            "WHERE (w.thread_id = :base OR w.thread_id LIKE :pedidos) "
            "AND w.checkpoint_ns = '' AND w.channel = '__interrupt__' "
            "AND w.checkpoint_id = (SELECT max(c.checkpoint_id) FROM checkpoints c "
            "WHERE c.thread_id = w.thread_id AND c.checkpoint_ns = '')"
        ),
        {"base": base, "pedidos": f"{base}:pedido:%"},
    )
    for thread in threads:
        checkpoint = await saver.aget_tuple({"configurable": {"thread_id": thread}})
        for _, canal, pausas in checkpoint.pending_writes if checkpoint else ():
            if canal == "__interrupt__":
                for pausa in pausas:
                    valor = pausa.value
                    if isinstance(valor, dict) and cartao in (
                        valor.get("aprovacao_id"),
                        valor.get("pergunta_id"),
                    ):
                        return thread, pausa.id
    return None


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
