"""Conserto de JSON (especificação §6.1 e §4, "Argumentos inválidos").

``ToolErrorMiddleware``: o erro de validação volta para o modelo tentar de novo
uma vez. Na saída estruturada, ``handle_errors`` do ``ToolStrategy``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware


def middleware_de_conserto() -> AgentMiddleware:
    """``ToolErrorMiddleware`` devolvendo o erro de validação ao modelo."""
    raise NotImplementedError


def mensagem_de_erro_de_validacao(erro: Exception) -> str:
    """Texto curto do erro de validação que o modelo recebe."""
    raise NotImplementedError
