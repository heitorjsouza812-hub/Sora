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
    raise NotImplementedError
