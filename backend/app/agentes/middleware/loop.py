"""Detector de loop (especificação §6, "Detector de loop"; §6.1).

Se a saída do modelo repetir a mesma linha 3 vezes seguidas, a chamada é
interrompida e refeita uma vez.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

REPETICOES_PARA_LOOP = 3


def tem_loop(texto: str, repeticoes: int = REPETICOES_PARA_LOOP) -> bool:
    """A mesma linha aparece ``repeticoes`` vezes seguidas."""
    raise NotImplementedError


class MiddlewareLoop(AgentMiddleware):
    """Refaz uma vez a chamada de modelo que entrou em loop."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Any:
        raise NotImplementedError
