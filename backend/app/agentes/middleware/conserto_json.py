"""Conserto de JSON (especificação §6.1 e §4, "Argumentos inválidos").

``ToolErrorMiddleware``: o erro de validação volta para o modelo tentar de novo
uma vez. Na saída estruturada, ``handle_errors`` do ``ToolStrategy``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware


def middleware_de_conserto() -> AgentMiddleware:
    """``ToolErrorMiddleware`` devolvendo o erro de validação ao modelo."""
    from langchain.agents.middleware import ToolErrorMiddleware

    def ao_erro(erro: Exception, _request: Any) -> str | None:
        if isinstance(erro, (ValidationError, TypeError, ValueError)):
            return mensagem_de_erro_de_validacao(erro)
        return None

    return ToolErrorMiddleware(on_error=ao_erro)


def mensagem_de_erro_de_validacao(erro: Exception) -> str:
    """Texto curto do erro de validação que o modelo recebe."""
    if isinstance(erro, ValidationError):
        detalhes = "; ".join(
            f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in erro.errors()[:5]
        )
    else:
        detalhes = str(erro)
    return f"Argumentos inválidos: {detalhes[:800]}. Corrija e tente uma vez de novo."
