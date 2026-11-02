"""Lembretes automáticos para Sora e agentes individuais."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app.agentes.prompts import carregar_prompt

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

CHAMADAS_ATE_LEMBRETE_DE_SILENCIO = 6


class MiddlewareLembretes(AgentMiddleware):
    """Injeta cada lembrete no máximo uma vez por execução."""

    def __init__(self) -> None:
        self._inicio_enviado = False
        self._silencio_enviado = False
        self._entrega_enviada = False

    @staticmethod
    def _mensagens(state: Any) -> list[Any]:
        return list(state.get("messages", [])) if isinstance(state, dict) else []

    @staticmethod
    def _nomes_de_ferramentas(mensagens: list[Any]) -> list[str]:
        nomes: list[str] = []
        for mensagem in mensagens:
            if isinstance(mensagem, AIMessage):
                nomes.extend(chamada.get("name", "") for chamada in mensagem.tool_calls)
        return nomes

    async def abefore_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        nomes = self._nomes_de_ferramentas(self._mensagens(state))
        if not self._inicio_enviado and "falar" not in nomes:
            self._inicio_enviado = True
            return {"messages": [SystemMessage(content=carregar_prompt("lembrete_inicio_turno"))]}
        chamadas_desde_falar = 0
        for nome in reversed(nomes):
            if nome == "falar":
                break
            chamadas_desde_falar += 1
        if chamadas_desde_falar >= CHAMADAS_ATE_LEMBRETE_DE_SILENCIO and not self._silencio_enviado:
            self._silencio_enviado = True
            return {"messages": [SystemMessage(content=carregar_prompt("lembrete_silencio"))]}
        return None

    async def aafter_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        if self._entrega_enviada:
            return None
        mensagens = self._mensagens(state)
        if not mensagens or isinstance(mensagens[-1], ToolMessage):
            return None
        nomes = self._nomes_de_ferramentas(mensagens)
        if nomes and nomes[-1] != "falar":
            self._entrega_enviada = True
            return {"messages": [SystemMessage(content=carregar_prompt("lembrete_entrega"))]}
        return None
