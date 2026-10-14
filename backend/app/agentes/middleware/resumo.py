"""Resumo de contexto (especificação §6.1; fase 2).

``SummarizationMiddleware`` com um modelo N1. Fica desligado na fase 1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.language_models import BaseChatModel


def middleware_de_resumo(modelo_n1: BaseChatModel) -> AgentMiddleware:
    """Resumo do histórico quando o contexto enche (fase 2)."""
    raise NotImplementedError
