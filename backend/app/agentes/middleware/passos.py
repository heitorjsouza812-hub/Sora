"""Evento ``passo`` do painel Trabalho (especificação §4, última regra; §2,
evento ``passo``; §1, tabela ``passos``).

Em volta de cada chamada de ferramenta de um especialista: grava o passo
``executando`` com o rótulo de ``app.ferramentas.rotulos`` (sem segredos),
emite ``passo``, e depois atualiza o mesmo passo com o resultado resumido e
o ``progresso`` da etapa.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest


class MiddlewarePassos(AgentMiddleware):
    """Grava e emite um passo por chamada de ferramenta."""

    def __init__(self, etapa_id: UUID, agente_id: UUID) -> None:
        raise NotImplementedError

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        raise NotImplementedError
