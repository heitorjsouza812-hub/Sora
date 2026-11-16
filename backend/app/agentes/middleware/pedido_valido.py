"""O pedido ao modelo sai num formato que o provedor aceita (Engrenagem; ``app/llm/esquemas.py``).

- antes de cada chamada: histórico sem chamada de ferramenta órfã (400 na OpenAI, Anthropic e
  Groq) e, para o Gemini, esquemas sem objeto aberto;
- antes de cada ferramenta: JSON em texto num campo que pede objeto ou lista é lido.

Fica por dentro da troca de modelo: quando um reserva de outro provedor responde, o ajuste é o
dele. Só muda o pedido desta chamada, nunca o estado salvo do agente.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)

from app.llm.esquemas import (
    argumentos_lidos,
    ferramenta_para_gemini,
    historico_valido,
    modelo_gemini,
)


def _nome_do_modelo(modelo: Any) -> str:
    return str(getattr(modelo, "model", None) or getattr(modelo, "model_name", "") or "")


def _esquema_da_ferramenta(ferramenta: Any) -> dict[str, Any] | None:
    from langchain_core.utils.function_calling import convert_to_openai_tool

    try:
        parametros = convert_to_openai_tool(ferramenta)["function"].get("parameters")
    except Exception:
        return None
    return parametros if isinstance(parametros, dict) else None


class MiddlewarePedidoValido(AgentMiddleware):
    def __init__(self) -> None:
        self._esquemas: dict[str, dict[str, Any] | None] = {}

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Any:
        mudancas: dict[str, Any] = {}
        mensagens = historico_valido(list(request.messages))
        if mensagens is not request.messages and mensagens != list(request.messages):
            mudancas["messages"] = mensagens
        if modelo_gemini(_nome_do_modelo(request.model)) and request.tools:
            from langchain_core.utils.function_calling import convert_to_openai_tool

            mudancas["tools"] = [
                ferramenta_para_gemini(convert_to_openai_tool(f)) for f in request.tools
            ]
        return await handler(request.override(**mudancas) if mudancas else request)

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[Any]]
    ) -> Any:
        ferramenta = request.tool
        argumentos = request.tool_call.get("args")
        if ferramenta is None or not isinstance(argumentos, dict) or not argumentos:
            return await handler(request)
        if ferramenta.name not in self._esquemas:
            self._esquemas[ferramenta.name] = _esquema_da_ferramenta(ferramenta)
        esquema = self._esquemas[ferramenta.name]
        if esquema is None:
            return await handler(request)
        lidos = argumentos_lidos(esquema, argumentos)
        if lidos == argumentos:
            return await handler(request)
        return await handler(request.override(tool_call={**request.tool_call, "args": lidos}))
