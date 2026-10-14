"""Cancelamento (especificação §6, "Cancelamento"; §6.1).

Antes de cada chamada de modelo ou ferramenta, confere a chave
``cancelar:{cadeia_id}`` no Redis e interrompe a tarefa em andamento.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest

if TYPE_CHECKING:
    from langgraph.runtime import Runtime


class CadeiaCancelada(Exception):
    """O usuário cancelou a cadeia."""


def chave_de_cancelamento(cadeia_id: UUID) -> str:
    """``cancelar:{cadeia_id}``."""
    raise NotImplementedError


class MiddlewareCancelamento(AgentMiddleware):
    """Interrompe o agente quando a cadeia é cancelada."""

    def __init__(self, cadeia_id: UUID) -> None:
        raise NotImplementedError

    async def abefore_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        raise NotImplementedError

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        raise NotImplementedError
