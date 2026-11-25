"""Encerra o turno quando o agente já deu o recado final (Âncora, rodada 4).

Sem isto, depois de cada ``falar`` o modelo é chamado de novo só para dizer "pronto": num
plano com limite de tokens por minuto isso custa chamadas à toa (7 para guardar uma memória).

O modelo indica a entrega com falar(final=True). Um aviso entre duas ações permite continuar.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, ToolMessage


def deve_encerrar(mensagens: list[Any]) -> bool:
    if not mensagens or not isinstance(mensagens[-1], ToolMessage):
        return False
    # Respostas de ferramenta da última chamada do modelo (as que fecham a AIMessage).
    fim = len(mensagens)
    inicio = fim
    while inicio > 0 and isinstance(mensagens[inicio - 1], ToolMessage):
        inicio -= 1
    if inicio == 0 or not isinstance(mensagens[inicio - 1], AIMessage):
        return False
    chamada = mensagens[inicio - 1]
    nomes = [c.get("name") for c in (chamada.tool_calls or [])]
    if not nomes or set(nomes) != {"falar"}:
        return False
    from app.agentes.middleware.fala_unica import JA_ENVIADA

    if any(m.content == JA_ENVIADA for m in mensagens[inicio:]):
        # O modelo repetiu uma fala já enviada (``fala_unica.py``): não há mais o que dizer.
        return True
    return (
        len(chamada.tool_calls) == 1
        and chamada.tool_calls[0]["args"].get("final") is True
        and all(m.status == "success" for m in mensagens[inicio:])
    )


class MiddlewareEncerraDepoisDeFalar(AgentMiddleware):
    @hook_config(can_jump_to=["end"])
    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        if deve_encerrar(list(state["messages"])):
            return {"jump_to": "end"}
        return None
