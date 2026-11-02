"""Limite de passos da etapa (especificação §6.1).

``ModelCallLimitMiddleware`` e ``ToolCallLimitMiddleware`` do LangChain, com
``run_limit``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware


def middleware_de_limites(
    max_chamadas_modelo: int, max_chamadas_ferramenta: int
) -> list[AgentMiddleware]:
    """Os dois limites configurados para uma execução da etapa."""
    if max_chamadas_modelo < 1 or max_chamadas_ferramenta < 1:
        raise ValueError("Os limites de chamadas precisam ser positivos.")
    from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

    return [
        ModelCallLimitMiddleware(run_limit=max_chamadas_modelo, exit_behavior="error"),
        ToolCallLimitMiddleware(run_limit=max_chamadas_ferramenta, exit_behavior="error"),
    ]
