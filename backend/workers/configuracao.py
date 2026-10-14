"""Configuração do worker ARQ (especificação §6; serviço ``worker`` do
docker-compose em §8.3).

O ARQ tenta de novo até 3 vezes; a saída de cada chamada de modelo fica
salva por ``(etapa_id, tentativa)`` (checkpointer), então a retomada não paga
de novo o que já foi feito.
"""

from __future__ import annotations

from typing import Any, ClassVar

from workers.aprovacoes import expirar_aprovacao
from workers.cadeia import (
    ajustar,
    avancar_cadeia,
    entregar_resultado,
    executar_etapa,
    planejar_cadeia,
    verificar_cadeia,
)
from workers.conversa import responder_direto


async def ao_iniciar(ctx: dict[str, Any]) -> None:
    """Abre banco, Redis e o checkpointer do LangGraph e guarda no ``ctx``."""
    raise NotImplementedError


async def ao_desligar(ctx: dict[str, Any]) -> None:
    """Fecha o que ``ao_iniciar`` abriu."""
    raise NotImplementedError


class WorkerSettings:
    """Lida pelo ``arq``. ``redis_settings`` entra quando o ``app/core`` tiver a
    configuração (``REDIS_URL``)."""

    functions: ClassVar[list[Any]] = [
        planejar_cadeia,
        avancar_cadeia,
        executar_etapa,
        verificar_cadeia,
        entregar_resultado,
        ajustar,
        responder_direto,
        expirar_aprovacao,
    ]
    on_startup = ao_iniciar
    on_shutdown = ao_desligar
    max_tries = 3
    job_timeout = 360
    """5 minutos da etapa + folga para gravar o erro."""
