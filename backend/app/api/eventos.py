"""Rotas SSE por conversa e por usuário; especificação §2.

- ``GET /v1/conversas/{id}/eventos``: tudo da conversa (texto e estado).
- ``GET /v1/eventos``: só eventos de estado de todas as conversas do usuário,
  com ``conversa_id`` em ``data`` (Ilha e barra lateral).

As duas retomam pelo cabeçalho ``Last-Event-ID``.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.eventos.sse import INTERVALO_PING_SEGUNDOS, gerar_sse, mensagem_ping
from app.eventos.streams import canal_conversa, canal_usuario
from app.modelos.tabelas import Conversa

roteador = APIRouter(tags=["eventos"], dependencies=[Depends(usuario_atual)])

RESPOSTA_SSE: dict[int | str, dict[str, object]] = {
    200: {
        "description": "Fluxo `text/event-stream` com eventos nomeados (`event:`) e `id` do Redis.",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    },
    404: {"description": "Conversa inexistente ou de outro usuário."},
}

CABECALHOS_SSE = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


async def conversa_do_usuario(sessao: AsyncSession, conversa_id: UUID, usuario_id: UUID) -> bool:
    """A conversa existe e é do usuário (toda consulta filtra por ``usuario_id``)."""
    consulta = select(Conversa.id).where(
        Conversa.id == conversa_id, Conversa.usuario_id == usuario_id
    )
    return (await sessao.execute(consulta)).scalar_one_or_none() is not None


@roteador.get(
    "/conversas/{conversa_id}/eventos",
    response_class=EventSourceResponse,
    responses=RESPOSTA_SSE,
)
async def eventos_da_conversa(
    conversa_id: UUID,
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(obter_sessao)],
    redis: Annotated[Redis, Depends(obter_redis)],
    ultimo_evento_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    """Transmite eventos de uma conversa retomando do último identificador."""
    if not await conversa_do_usuario(sessao, conversa_id, usuario_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada.")
    return EventSourceResponse(
        gerar_sse(redis, canal_conversa(conversa_id), ultimo_evento_id),
        headers=CABECALHOS_SSE,
        ping=INTERVALO_PING_SEGUNDOS,
        ping_message_factory=mensagem_ping,
    )


@roteador.get("/eventos", response_class=EventSourceResponse, responses=RESPOSTA_SSE)
async def eventos_do_usuario(
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    redis: Annotated[Redis, Depends(obter_redis)],
    ultimo_evento_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    """Transmite eventos de estado para a Ilha e a barra lateral."""
    return EventSourceResponse(
        gerar_sse(redis, canal_usuario(usuario_id), ultimo_evento_id),
        headers=CABECALHOS_SSE,
        ping=INTERVALO_PING_SEGUNDOS,
        ping_message_factory=mensagem_ping,
    )
