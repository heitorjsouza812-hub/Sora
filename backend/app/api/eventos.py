"""Rotas SSE por conversa e por usuário; especificação §2."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sse_starlette.sse import EventSourceResponse

from app.core.dependencias import usuario_atual

roteador = APIRouter(tags=["eventos"], dependencies=[Depends(usuario_atual)])

RESPOSTA_SSE: dict[int | str, dict[str, object]] = {
    200: {
        "description": "Fluxo `text/event-stream` com eventos nomeados (`event:`) e `id` do Redis.",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }
}


@roteador.get(
    "/conversas/{conversa_id}/eventos",
    response_class=EventSourceResponse,
    responses=RESPOSTA_SSE,
)
async def eventos_da_conversa(
    conversa_id: UUID,
    requisicao: Request,
    ultimo_evento_id: str | None = Header(None, alias="Last-Event-ID"),
) -> EventSourceResponse:
    """Transmite eventos de uma conversa retomando do último identificador."""
    raise NotImplementedError


@roteador.get("/eventos", response_class=EventSourceResponse, responses=RESPOSTA_SSE)
async def eventos_do_usuario(
    requisicao: Request,
    ultimo_evento_id: str | None = Header(None, alias="Last-Event-ID"),
) -> EventSourceResponse:
    """Transmite eventos de estado para a Ilha e a barra lateral."""
    raise NotImplementedError
