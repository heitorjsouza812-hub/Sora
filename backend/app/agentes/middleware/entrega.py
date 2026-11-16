"""Especialista da cadeia que responde em texto puro ganha uma segunda chance (Engrenagem).

O motor não usa ``tool_choice``: o modelo pode responder só com texto. Para a Sora e o bot 1:1 o
worker fala esse texto por ele; para o bot de grupo o texto vira o fim do turno. Já o
especialista da cadeia (pesquisador, redator, designer, verificador) só termina de verdade com
``entregar``/``veredito``: com texto puro o laço acabava e a etapa falhava com "o bot terminou
sem entregar", jogando fora o trabalho (modelos pequenos fazem isso com frequência).

Em vez de ``tool_choice="required"`` (nem todo provedor aceita, e a Anthropic com raciocínio
recusa), o agente recebe um aviso e volta ao modelo, uma vez por execução.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, SystemMessage

AVISO_SEM_ENTREGA = (
    "Aviso do sistema: você respondeu só com texto, e ninguém recebe texto solto. Para terminar a "
    "etapa chame agora a ferramenta `{ferramenta}` com o resultado (pode usar o texto que você "
    "acabou de escrever)."
)


class MiddlewareExigeEntrega(AgentMiddleware):
    def __init__(self, ferramenta: str, tentativas: int = 1) -> None:
        self.ferramenta = ferramenta
        self.tentativas = tentativas
        self._avisos = 0

    @hook_config(can_jump_to=["model"])
    async def aafter_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        mensagens = state.get("messages") if isinstance(state, dict) else None
        if not mensagens or self._avisos >= self.tentativas:
            return None
        ultima = mensagens[-1]
        if not isinstance(ultima, AIMessage) or ultima.tool_calls:
            return None
        self._avisos += 1
        return {
            "messages": [SystemMessage(AVISO_SEM_ENTREGA.format(ferramenta=self.ferramenta))],
            "jump_to": "model",
        }
