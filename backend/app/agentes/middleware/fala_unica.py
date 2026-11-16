"""Uma fala não sai duas vezes no mesmo turno (Engrenagem).

O prompt manda a primeira ação de todo turno ser ``falar``; para um pedido simples essa primeira
fala já é a resposta inteira. Como o primeiro ``falar`` sozinho é tratado como aviso
(``encerra_depois_de_falar.py``), o modelo é chamado de novo e modelos pequenos (Groq) costumam
chamar ``falar`` outra vez com o MESMO texto: o usuário via a resposta repetida segundos depois.
O mesmo acontece quando o modelo manda duas chamadas ``falar`` iguais na mesma resposta (elas
rodam em paralelo).

Aqui, antes de rodar ``falar``, o texto é comparado (sem diferença de espaços e maiúsculas) com o
que já foi falado neste turno (desde a última mensagem do usuário) e com as chamadas ``falar``
anteriores da mesma resposta do modelo. Repetido: a ferramenta não roda, o modelo recebe
``JA_ENVIADA`` e o turno termina (``deve_encerrar``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

JA_ENVIADA = "Esta mensagem já tinha sido enviada ao usuário neste turno; não foi repetida."


def texto_normalizado(texto: Any) -> str:
    return " ".join(str(texto or "").split()).casefold()


def _texto_da_chamada(chamada: dict[str, Any]) -> str:
    args = chamada.get("args")
    return texto_normalizado(args.get("texto") if isinstance(args, dict) else "")


def fala_repetida(mensagens: list[Any], chamada: dict[str, Any]) -> bool:
    """``chamada`` (um ``falar``) repete uma fala já enviada neste turno ou uma chamada ``falar``
    anterior da mesma resposta do modelo."""
    texto = _texto_da_chamada(chamada)
    if not texto:
        return False
    enviadas: set[str] = set()  # ids de ``falar`` que de fato rodaram neste turno
    for mensagem in reversed(mensagens):
        if isinstance(mensagem, HumanMessage):
            break
        if (
            isinstance(mensagem, ToolMessage)
            and mensagem.name == "falar"
            and mensagem.status != "error"
            and mensagem.content != JA_ENVIADA
        ):
            enviadas.add(mensagem.tool_call_id)
    for mensagem in reversed(mensagens):
        if isinstance(mensagem, HumanMessage):
            break
        if not isinstance(mensagem, AIMessage):
            continue
        anteriores = mensagem.tool_calls or []
        ids = [c.get("id") for c in anteriores]
        if chamada.get("id") in ids:
            # A mesma resposta do modelo: só as chamadas que vêm antes desta contam.
            anteriores = anteriores[: ids.index(chamada.get("id"))]
            for irma in anteriores:
                if irma.get("name") == "falar" and _texto_da_chamada(irma) == texto:
                    return True
            continue
        for anterior in anteriores:
            if (
                anterior.get("name") == "falar"
                and anterior.get("id") in enviadas
                and _texto_da_chamada(anterior) == texto
            ):
                return True
    return False


class MiddlewareFalaUnica(AgentMiddleware):
    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[Any]]
    ) -> Any:
        chamada = request.tool_call
        if chamada.get("name") != "falar":
            return await handler(request)
        estado = request.state
        mensagens = estado.get("messages", []) if isinstance(estado, dict) else []
        if fala_repetida(list(mensagens), dict(chamada)):
            return ToolMessage(content=JA_ENVIADA, tool_call_id=chamada["id"], name="falar")
        return await handler(request)
