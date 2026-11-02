"""Fila de jobs (especificação §6: "os jobs ficam atrás de uma função
``enfileirar(job, **args)`` nossa").

Todo código que põe trabalho na fila (API, jobs, ferramentas) usa só
``enfileirar``; ninguém importa o ARQ fora de ``workers/``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import obter_configuracao

NomeJob = Literal[
    "planejar_cadeia",
    "avancar_cadeia",
    "executar_etapa",
    "verificar_cadeia",
    "entregar_resultado",
    "ajustar",
    "responder_direto",
    "retomar_conversa",
    "despachar_equipe",
    "executar_item_fila",
    "executar_tarefa_canal",
    "expirar_aprovacao",
    # adaptados do Rakazo (docs/referencias/rakazo.md)
    "executar_rotina",
    "compactar_historico",
    "responder_canal",
    "reconciliar_travados",
]

_fila: ArqRedis | None = None


def configurar_fila(fila: ArqRedis | None) -> None:
    """Injeta a conexao compartilhada; ``None`` limpa no desligamento/teste."""
    global _fila
    _fila = fila


async def obter_fila() -> ArqRedis:
    """Devolve a fila compartilhada, abrindo-a sob demanda para a API."""
    global _fila
    if _fila is None:
        _fila = await create_pool(RedisSettings.from_dsn(obter_configuracao().redis_url))
    return _fila


async def enfileirar(
    job: NomeJob,
    *,
    id_job: str | None = None,
    agendar_para: datetime | None = None,
    **args: Any,
) -> None:
    """Põe o job na fila. ``id_job`` evita duplicar; ``agendar_para`` adia
    (usado por ``expirar_aprovacao``)."""
    fila = await obter_fila()
    await fila.enqueue_job(job, _job_id=id_job, _defer_until=agendar_para, **args)
