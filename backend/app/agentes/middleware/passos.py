"""Porta do middleware para registrar os passos do painel Trabalho."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langgraph.errors import GraphBubbleUp

PAUSADO_PARA_APROVACAO = "Aguardando a sua resposta."

IniciarPasso = Callable[[UUID, UUID, dict[str, Any]], Awaitable[Any]]
FinalizarPasso = Callable[[Any, Any | None, BaseException | None], Awaitable[None]]


class MiddlewarePassos(AgentMiddleware):
    def __init__(
        self, etapa_id: UUID, agente_id: UUID, *, iniciar: IniciarPasso, finalizar: FinalizarPasso
    ) -> None:
        self.etapa_id = etapa_id
        self.agente_id = agente_id
        self._iniciar = iniciar
        self._finalizar = finalizar

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[Any]]
    ) -> Any:
        passo = await self._iniciar(self.etapa_id, self.agente_id, dict(request.tool_call))
        try:
            resultado = await handler(request)
        except GraphBubbleUp:
            # Pausa legítima (cartão de aprovação, pergunta): não é falha da ferramenta. O passo
            # fecha como "aguardando a aprovação" e, na retomada, a ferramenta ganha outro passo.
            await self._finalizar(passo, PAUSADO_PARA_APROVACAO, None)
            raise
        except BaseException as erro:
            await self._finalizar(passo, None, erro)
            raise
        await self._finalizar(passo, resultado, None)
        return resultado
