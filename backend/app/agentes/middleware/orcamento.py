"""Reserva e correção do orçamento de tokens em volta de cada chamada."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages.utils import count_tokens_approximately

ReservarTokens = Callable[[UUID, int, int], Awaitable[bool]]
CorrigirTokens = Callable[[UUID, int, int], Awaitable[None]]


class OrcamentoEstourado(Exception):
    """A reserva passaria do orçamento da cadeia."""


class MiddlewareOrcamento(AgentMiddleware):
    def __init__(
        self,
        cadeia_id: UUID,
        orcamento_tokens: int,
        *,
        reservar: ReservarTokens,
        corrigir: CorrigirTokens,
    ) -> None:
        if orcamento_tokens < 1:
            raise ValueError("O orçamento de tokens precisa ser positivo.")
        self.cadeia_id = cadeia_id
        self.orcamento_tokens = orcamento_tokens
        self._reservar = reservar
        self._corrigir = corrigir

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> Any:
        estimativa = estimar_tokens(request)
        if not await self._reservar(self.cadeia_id, estimativa, self.orcamento_tokens):
            raise OrcamentoEstourado("A próxima chamada passaria do orçamento da cadeia.")
        try:
            resposta = await handler(request)
        except BaseException:
            await self._corrigir(self.cadeia_id, estimativa, 0)
            raise
        real = sum(
            int((getattr(m, "usage_metadata", None) or {}).get("total_tokens", 0))
            for m in resposta.result
        )
        await self._corrigir(self.cadeia_id, estimativa, real or estimativa)
        return resposta


def estimar_tokens(request: ModelRequest) -> int:
    prompt = count_tokens_approximately(request.messages)
    maximo_saida = int((request.model_settings or {}).get("max_tokens", 1024))
    return max(1, prompt + maximo_saida)
