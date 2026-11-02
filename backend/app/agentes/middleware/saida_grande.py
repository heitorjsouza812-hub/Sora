"""Move saídas grandes para armazenamento persistente por uma porta injetada."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage

LINHAS_DE_AMOSTRA = 40
SalvarSaida = Callable[[UUID | None, str], Awaitable[str]]


class MiddlewareSaidaGrande(AgentMiddleware):
    def __init__(
        self, cadeia_id: UUID | None, *, salvar: SalvarSaida, limite_caracteres: int = 20_000
    ) -> None:
        if limite_caracteres < 1:
            raise ValueError("O limite da saída precisa ser positivo.")
        self.cadeia_id = cadeia_id
        self._salvar = salvar
        self.limite_caracteres = limite_caracteres

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[Any]]
    ) -> Any:
        resultado = await handler(request)
        if not isinstance(resultado, ToolMessage) or not isinstance(resultado.content, str):
            return resultado
        if len(resultado.content) <= self.limite_caracteres:
            return resultado
        caminho = await self._salvar(self.cadeia_id, resultado.content)
        amostra = "\n".join(resultado.content.splitlines()[:LINHAS_DE_AMOSTRA])
        return resultado.model_copy(
            update={
                "content": f"Resultado completo salvo em {caminho}. Primeiras linhas:\n{amostra}"
            }
        )
