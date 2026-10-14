"""Conversão de eventos internos para mensagens SSE; especificação §2."""

from collections.abc import AsyncIterator
from typing import Any


async def gerar_sse(canal: str, ultimo_evento_id: str | None) -> AsyncIterator[dict[str, Any]]:
    """Gera mensagens SSE com id, event e data serializada."""
    raise NotImplementedError
    yield  # pragma: no cover
