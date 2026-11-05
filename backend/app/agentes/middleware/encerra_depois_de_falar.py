"""Encerra o turno quando o agente já deu o recado final (Âncora, rodada 4).

Sem isto, depois de cada ``falar`` o modelo é chamado de novo só para dizer "pronto": num
plano com limite de tokens por minuto isso custa chamadas à toa (7 para guardar uma memória).

Regra: o turno termina depois de um ``falar`` que veio **sozinho** na chamada do modelo e que
**não é o primeiro passo do turno** (já houve outra ferramenta ou outro ``falar`` antes). O
primeiro ``falar`` sozinho é aviso ("vou guardar...") e o agente segue para a ferramenta.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


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
    # Há algo de ferramenta antes dela neste turno (desde a última mensagem do usuário)?
    anteriores = mensagens[: inicio - 1]
    for mensagem in reversed(anteriores):
        if isinstance(mensagem, HumanMessage):
            return False
        if isinstance(mensagem, ToolMessage):
            return True
    return False


class MiddlewareEncerraDepoisDeFalar(AgentMiddleware):
    @hook_config(can_jump_to=["end"])
    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        if deve_encerrar(list(state["messages"])):
            return {"jump_to": "end"}
        return None
