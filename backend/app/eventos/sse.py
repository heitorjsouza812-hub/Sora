"""Conversão dos eventos do Redis Stream em mensagens SSE; especificação §2.

Cada mensagem leva ``id`` (o do stream), ``event`` e ``data`` (JSON). O
``ping`` sai a cada 15 segundos pelo próprio ``EventSourceResponse``, **sem**
``id``: assim ele não mexe no ``Last-Event-ID`` que o app guarda para reconectar.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

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
    expira_em: float | None = None,
    a_cada_volta: Callable[[], Awaitable[None]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Gera as mensagens SSE do canal, retomando do ``Last-Event-ID``.

    ``expira_em`` (epoch do ``exp`` do token): o stream termina quando o token vence; o app
    reconecta com um token novo e retoma do ``Last-Event-ID`` (API-08/VAL-10). A checagem roda
    a cada evento e a cada ``bloquear_ms`` sem evento. ``a_cada_volta`` renova o registro da
    conexão (limite por usuário).
    """
    async for evento in ler_eventos(redis, canal, ultimo_evento_id, bloquear_ms=bloquear_ms):
        if expira_em is not None and time.time() >= expira_em:
            return
        if a_cada_volta is not None:
            await a_cada_volta()
        if evento is not None:
            yield mensagem_sse(evento)


# ---------------------------------------------------------------- limite de conexões (API-01)

MAX_CONEXOES_POR_USUARIO = 10
"""Streams SSE abertos ao mesmo tempo por usuário (abas, Ilha, desktop)."""
VALIDADE_CONEXAO_SEGUNDOS = 60
"""Uma conexão que não se renova nesse prazo (processo caiu) deixa de contar."""


def _chave_conexoes(usuario_id: UUID) -> str:
    return f"sse:conexoes:{usuario_id}"


async def registrar_conexao(redis: Redis, usuario_id: UUID) -> str | None:
    """Reserva uma vaga de stream para o usuário; ``None`` se ele já está no limite."""
    chave, agora = _chave_conexoes(usuario_id), time.time()
    await redis.zremrangebyscore(chave, 0, agora - VALIDADE_CONEXAO_SEGUNDOS)
    if await redis.zcard(chave) >= MAX_CONEXOES_POR_USUARIO:
        return None
    conexao = uuid4().hex
    await redis.zadd(chave, {conexao: agora})
    await redis.expire(chave, VALIDADE_CONEXAO_SEGUNDOS * 2)
    return conexao


async def renovar_conexao(redis: Redis, usuario_id: UUID, conexao: str) -> None:
    chave = _chave_conexoes(usuario_id)
    await redis.zadd(chave, {conexao: time.time()})
    await redis.expire(chave, VALIDADE_CONEXAO_SEGUNDOS * 2)


async def encerrar_conexao(redis: Redis, usuario_id: UUID, conexao: str) -> None:
    await redis.zrem(_chave_conexoes(usuario_id), conexao)
