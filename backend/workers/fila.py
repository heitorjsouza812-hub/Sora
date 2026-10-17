"""Fila de jobs (especificação §6: "os jobs ficam atrás de uma função
``enfileirar(job, **args)`` nossa").

Todo código que põe trabalho na fila (API, jobs, ferramentas) usa só
``enfileirar``; ninguém importa o ARQ fora de ``workers/``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

NomeJob = Literal[
    "planejar_cadeia",
    "avancar_cadeia",
    "executar_etapa",
    "verificar_cadeia",
    "entregar_resultado",
    "ajustar",
    "responder_direto",
    "expirar_aprovacao",
    # adaptados do Rakazo (docs/referencias/rakazo.md)
    "executar_rotina",
    "compactar_historico",
    "responder_canal",
    "reconciliar_travados",
]


async def enfileirar(
    job: NomeJob,
    *,
    id_job: str | None = None,
    agendar_para: datetime | None = None,
    **args: Any,
) -> None:
    """Põe o job na fila. ``id_job`` evita duplicar; ``agendar_para`` adia
    (usado por ``expirar_aprovacao``)."""
    raise NotImplementedError
