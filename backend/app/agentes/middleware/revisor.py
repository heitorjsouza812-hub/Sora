"""Aprovação na execução de cada ferramenta (Âncora, etapa 4): política + juiz do revisor.

A regra está em ``app/revisor/execucao.py``; este middleware só a coloca em volta de cada
chamada. Se a ferramenta não pode rodar (negada, sem supervisão), o modelo recebe o motivo
como resultado e segue; a interrupção do cartão passa direto para o LangGraph.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage

from app.ferramentas.base import ContextoFerramenta


class MiddlewareRevisor(AgentMiddleware):
    def __init__(self, contexto: ContextoFerramenta) -> None:
        self.contexto = contexto

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[Any]]
    ) -> Any:
        from app.revisor.execucao import conferir_acao

        chamada = request.tool_call
        nome = str(chamada.get("name", ""))
        argumentos = chamada.get("args") if isinstance(chamada.get("args"), dict) else {}
        metadados = getattr(request.tool, "metadata", None) or {}
        resultado = await conferir_acao(
            nome,
            dict(argumentos),
            self.contexto,
            chamada_id=str(chamada.get("id", "")),
            somente_leitura=metadados.get("somente_leitura"),
        )
        if resultado is not None:
            return ToolMessage(
                content=resultado, tool_call_id=str(chamada.get("id", "")), name=nome
            )
        return await handler(request)
