"""Orçamento de tokens (especificação §6, "Orçamento"; §6.1).

Antes de cada chamada de modelo, reserva a estimativa de tokens com ``INCRBY``
no Redis. Se passar do ``orcamento_tokens``, a cadeia vai para
``aguardando_usuario`` e a Sora pergunta se pode continuar. Depois da chamada,
o valor real (custo do LiteLLM) corrige a reserva e é gravado em
``chamadas_modelo``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse


class OrcamentoEstourado(Exception):
    """A reserva passaria do orçamento da cadeia."""


class MiddlewareOrcamento(AgentMiddleware):
    """Reserva e corrige o gasto de tokens da cadeia em volta de cada chamada."""

    def __init__(self, cadeia_id: UUID, orcamento_tokens: int) -> None:
        raise NotImplementedError

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Any:
        raise NotImplementedError


def estimar_tokens(request: ModelRequest) -> int:
    """Estimativa de tokens da chamada (prompt + saída máxima)."""
    raise NotImplementedError
