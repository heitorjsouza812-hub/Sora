"""Saída grande em arquivo (especificação §4: resultado com mais de 20.000
caracteres vai para um arquivo, e o modelo recebe o caminho e as primeiras
linhas).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest

LINHAS_DE_AMOSTRA = 40


class MiddlewareSaidaGrande(AgentMiddleware):
    """Troca resultados grandes por caminho + primeiras linhas."""

    def __init__(self, cadeia_id: UUID | None, limite_caracteres: int = 20_000) -> None:
        raise NotImplementedError

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        raise NotImplementedError
