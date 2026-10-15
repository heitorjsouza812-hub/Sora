"""Rotas SSE por conversa e por usuário; especificação §2.

- ``GET /v1/conversas/{id}/eventos``: tudo da conversa (texto e estado).
- ``GET /v1/eventos``: só eventos de estado de todas as conversas do usuário,
  com ``conversa_id`` em ``data`` (Ilha e barra lateral).

As duas retomam pelo cabeçalho ``Last-Event-ID``.
"""

from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.eventos.sse import (
    INTERVALO_PING_SEGUNDOS,
    VALIDADE_CONEXAO_SEGUNDOS,
    encerrar_conexao,
    gerar_sse,
    mensagem_ping,
    registrar_conexao,
    renovar_conexao,
)
from app.eventos.streams import canal_conversa, canal_usuario
from app.modelos.tabelas import Conversa

roteador = APIRouter(tags=["eventos"], dependencies=[Depends(usuario_atual)])

RESPOSTA_SSE: dict[int | str, dict[str, object]] = {
    200: {
        "description": "Fluxo `text/event-stream` com eventos nomeados (`event:`) e `id` do Redis.",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    },
    404: {"description": "Conversa inexistente ou de outro usuário."},
    429: {"description": "O usuário já tem o máximo de streams abertos."},
}

CABECALHOS_SSE = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


async def conversa_do_usuario(sessao: AsyncSession, conversa_id: UUID, usuario_id: UUID) -> bool:
    """A conversa existe e é do usuário (toda consulta filtra por ``usuario_id``)."""
    consulta = select(Conversa.id).where(
        Conversa.id == conversa_id, Conversa.usuario_id == usuario_id
    )
    return (await sessao.execute(consulta)).scalar_one_or_none() is not None


def validade_do_token(requisicao: Request) -> float | None:
    """``exp`` do token de acesso guardado por ``usuario_atual`` (``None`` se não houver)."""
    return getattr(requisicao.state, "token_expira_em", None)


async def _transmitir(
    redis: Redis,
    canal: str,
    ultimo_evento_id: str | None,
    usuario_id: UUID,
    expira_em: float | None,
) -> EventSourceResponse:
    """Reserva a vaga de stream do usuário (429 se cheio) e devolve o SSE que a libera ao
    terminar; o stream acaba quando o token vence (API-01, API-08)."""
    conexao = await registrar_conexao(redis, usuario_id)
    if conexao is None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Conexões de eventos demais abertas. Feche alguma aba e tente de novo.",
            headers={"Retry-After": str(VALIDADE_CONEXAO_SEGUNDOS)},
        )

    async def renovar() -> None:
        await renovar_conexao(redis, usuario_id, conexao)

    async def fluxo() -> AsyncIterator[dict[str, Any]]:
        try:
            async for mensagem in gerar_sse(
                redis, canal, ultimo_evento_id, expira_em=expira_em, a_cada_volta=renovar
            ):
                yield mensagem
        finally:
            await encerrar_conexao(redis, usuario_id, conexao)

    return EventSourceResponse(
        fluxo(),
        headers=CABECALHOS_SSE,
        ping=INTERVALO_PING_SEGUNDOS,
        ping_message_factory=mensagem_ping,
    )


@roteador.get(
    "/conversas/{conversa_id}/eventos",
    response_class=EventSourceResponse,
    responses=RESPOSTA_SSE,
)
async def eventos_da_conversa(
    conversa_id: UUID,
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    # scope="function": a sessão (e a conexão do pool) fecha antes do stream começar; com o
    # padrão ("request") ela ficaria presa enquanto o SSE durasse (API-01).
    sessao: Annotated[AsyncSession, Depends(obter_sessao, scope="function")],
    redis: Annotated[Redis, Depends(obter_redis)],
    ultimo_evento_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    expira_em: Annotated[float | None, Depends(validade_do_token)] = None,
) -> EventSourceResponse:
    """Transmite eventos de uma conversa retomando do último identificador."""
    if not await conversa_do_usuario(sessao, conversa_id, usuario_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada.")
    return await _transmitir(
        redis, canal_conversa(conversa_id), ultimo_evento_id, usuario_id, expira_em
    )


@roteador.get("/eventos", response_class=EventSourceResponse, responses=RESPOSTA_SSE)
async def eventos_do_usuario(
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    redis: Annotated[Redis, Depends(obter_redis)],
    ultimo_evento_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    expira_em: Annotated[float | None, Depends(validade_do_token)] = None,
) -> EventSourceResponse:
    """Transmite eventos de estado para a Ilha e a barra lateral."""
    return await _transmitir(
        redis, canal_usuario(usuario_id), ultimo_evento_id, usuario_id, expira_em
    )
