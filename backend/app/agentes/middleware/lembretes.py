"""Lembretes automáticos (03-prompts, "Lembretes automáticos"; especificação §6.1).

Injeta mensagens ``visivel = false``, no máximo uma de cada por turno:
início de turno (a primeira chamada não foi ``falar``), silêncio (6 chamadas
de ferramenta seguidas sem ``falar``) e entrega (vai encerrar e o último
``falar`` foi só a confirmação inicial). Só para a Sora e agentes individuais.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

CHAMADAS_ATE_LEMBRETE_DE_SILENCIO = 6


class MiddlewareLembretes(AgentMiddleware):
    """Injeta os lembretes de início de turno, silêncio e entrega."""

    async def abefore_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        raise NotImplementedError

    async def aafter_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        raise NotImplementedError
