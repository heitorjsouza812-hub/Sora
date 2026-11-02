"""Cerca de dado não confiável (03-prompts, "cerca de dado não confiável";
especificação §4).

Todo resultado de ``buscar_web``, ``ler_pagina``, ``ler_anexo`` (e
``chamar_conector`` na fase 3) entra em ``<dado_externo origem="...">``, depois
de neutralizar qualquer ``<dado_externo`` que já venha no conteúdo.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage

from app.agentes.prompts import cercar

FERRAMENTAS_COM_CERCA = frozenset({"buscar_web", "ler_pagina", "ler_anexo", "chamar_conector"})


class MiddlewareCerca(AgentMiddleware):
    """Cerca o resultado das ferramentas de ``FERRAMENTAS_COM_CERCA``."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        resultado = await handler(request)
        nome = request.tool_call["name"]
        if nome not in FERRAMENTAS_COM_CERCA or not isinstance(resultado, ToolMessage):
            return resultado
        if not isinstance(resultado.content, str):
            return resultado
        return resultado.model_copy(update={"content": cercar(resultado.content, nome)})
