"""Prazo por ferramenta (especificação §4 e §6, "Prazos": 2 minutos por chamada
de ferramenta). O prazo de 5 minutos da etapa fica no job ``executar_etapa``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest


class MiddlewarePrazoFerramenta(AgentMiddleware):
    """Corta a ferramenta que passa do prazo e devolve o erro ao modelo."""

    def __init__(self, prazo_segundos: float = 120) -> None:
        raise NotImplementedError

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        raise NotImplementedError
