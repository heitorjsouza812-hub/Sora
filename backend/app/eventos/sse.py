"""Conversão dos eventos do Redis Stream em mensagens SSE; especificação §2.

Cada mensagem leva ``id`` (o do stream), ``event`` e ``data`` (JSON). O
``ping`` sai a cada 15 segundos pelo próprio ``EventSourceResponse``, **sem**
``id``: assim ele não mexe no ``Last-Event-ID`` que o app guarda para reconectar.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sse_starlette.event import ServerSentEvent

from app.eventos.streams import EventoLido, ler_eventos

if TYPE_CHECKING:
    from redis.asyncio import Redis

INTERVALO_PING_SEGUNDOS = 15
BLOQUEIO_XREAD_MS = 5_000
"""Quanto cada ``XREAD`` espera antes de tentar de novo (não muda nada para o app)."""


def mensagem_ping() -> ServerSentEvent:
    """O evento ``ping`` da §2: sem ``id`` e com ``data`` vazio."""
    return ServerSentEvent(event="ping", data="{}")


def mensagem_sse(evento: EventoLido) -> dict[str, Any]:
    """Formato aceito pelo ``EventSourceResponse`` do sse-starlette."""
    return {
        "id": evento.id,
        "event": evento.evento,
        "data": json.dumps(evento.dados, ensure_ascii=False, separators=(",", ":")),
    }


async def gerar_sse(
    redis: Redis,
    canal: str,
    ultimo_evento_id: str | None,
    *,
    bloquear_ms: int = BLOQUEIO_XREAD_MS,
) -> AsyncIterator[dict[str, Any]]:
    """Gera as mensagens SSE do canal, retomando do ``Last-Event-ID``."""
    async for evento in ler_eventos(redis, canal, ultimo_evento_id, bloquear_ms=bloquear_ms):
        if evento is not None:
            yield mensagem_sse(evento)
