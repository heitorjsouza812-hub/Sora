"""Entrega ao especialista as mensagens enviadas enquanto ele trabalha."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

if TYPE_CHECKING:
    from langgraph.runtime import Runtime


class MiddlewareMensagensPendentes(AgentMiddleware):
    """Antes de cada chamada de modelo, esvazia o correio da etapa e injeta o que chegou."""

    def __init__(self, etapa_id: UUID, *, ler: Callable[[UUID], Awaitable[list[str]]]) -> None:
        self._etapa_id = etapa_id
        self._ler = ler

    async def abefore_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        textos = await self._ler(self._etapa_id)
        if not textos:
            return None
        return {
            "messages": [
                HumanMessage(content=f"<mensagem_da_sora>{t}</mensagem_da_sora>") for t in textos
            ]
        }
