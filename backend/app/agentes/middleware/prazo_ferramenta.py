"""Prazo por ferramenta (especificação §4 e §6, "Prazos": 2 minutos por chamada
de ferramenta). O prazo de 5 minutos da etapa fica no job ``executar_etapa``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage


class MiddlewarePrazoFerramenta(AgentMiddleware):
    """Corta a ferramenta que passa do prazo e devolve o erro ao modelo."""

    def __init__(self, prazo_segundos: float = 120) -> None:
        if prazo_segundos <= 0:
            raise ValueError("O prazo da ferramenta precisa ser positivo.")
        self.prazo_segundos = prazo_segundos

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        try:
            async with asyncio.timeout(self.prazo_segundos):
                return await handler(request)
        except TimeoutError:
            return ToolMessage(
                content=f"A ferramenta excedeu o prazo de {self.prazo_segundos:g} segundos.",
                tool_call_id=request.tool_call["id"],
                name=request.tool_call["name"],
                status="error",
            )
