"""Cancelamento (especificação §6, "Cancelamento"; §6.1).

Antes de cada chamada de modelo ou ferramenta, confere a chave
``cancelar:{cadeia_id}`` no Redis e interrompe a tarefa em andamento.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest

from app.orquestrador.cadeia import chave_de_cancelamento

if TYPE_CHECKING:
    from langgraph.runtime import Runtime


__all__ = ["CadeiaCancelada", "MiddlewareCancelamento", "chave_de_cancelamento"]


class CadeiaCancelada(Exception):
    """O usuário cancelou a cadeia."""


class MiddlewareCancelamento(AgentMiddleware):
    """Interrompe o agente quando a cadeia é cancelada."""

    def __init__(
        self, cadeia_id: UUID, *, esta_cancelada: Callable[[UUID], Awaitable[bool]]
    ) -> None:
        self.cadeia_id = cadeia_id
        self._esta_cancelada = esta_cancelada

    async def _conferir(self) -> None:
        if await self._esta_cancelada(self.cadeia_id):
            raise CadeiaCancelada(f"A cadeia {self.cadeia_id} foi cancelada.")

    async def abefore_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        await self._conferir()
        return None

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        await self._conferir()
        return await handler(request)
