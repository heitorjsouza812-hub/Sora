"""Engrenagem: nova tentativa depois de um 429 continua de onde a thread parou.

O worker do grupo repete o turno inteiro depois de esperar o limite. Mandar a entrada de novo
acrescentava o pedido outra vez ao histórico (o modelo via o pedido duas vezes e refazia as
ferramentas que já tinham rodado). Com ``continuar_se_parou`` o grafo segue do passo que falhou.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from app.agentes.montagem import ContextoAgente, rodar_etapa


class FalhaUmaVez(GenericFakeChatModel):
    falhou: bool = False

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
        if len(messages) >= 3 and not self.falhou:  # depois da ferramenta: "429"
            self.falhou = True
            raise RuntimeError("429")
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


@pytest.mark.parametrize("continuar", [True, False])
async def test_nova_tentativa_nao_repete_o_pedido_nem_a_ferramenta(continuar: bool) -> None:
    execucoes: list[str] = []

    @tool
    async def agir(x: str) -> str:
        """Faz algo com efeito."""
        execucoes.append(x)
        return "feito"

    modelo = FalhaUmaVez(
        messages=iter(
            [
                AIMessage("", tool_calls=[{"name": "agir", "args": {"x": "a"}, "id": "c1"}]),
                AIMessage("pronto"),
            ]
        )
    )
    agente = create_agent(modelo, tools=[agir], checkpointer=InMemorySaver())
    contexto = ContextoAgente(
        usuario_id=uuid4(),
        agente_id=uuid4(),
        conversa_id=uuid4(),
        papel="canal",
        thread_proprio=f"canal:{uuid4()}",
    )
    # Como no worker: cada tentativa monta a entrada de novo (mensagem nova, id novo).
    with pytest.raises(RuntimeError):
        await rodar_etapa(agente, contexto, {"messages": [HumanMessage("faça")]})
    resultado = await rodar_etapa(
        agente, contexto, {"messages": [HumanMessage("faça")]}, continuar_se_parou=continuar
    )
    pedidos = [m for m in resultado["messages"] if isinstance(m, HumanMessage)]
    assert execucoes == ["a"]
    assert resultado["messages"][-1].content == "pronto"
    assert len(pedidos) == (1 if continuar else 2)  # sem continuar: o pedido aparecia 2 vezes


async def test_continuar_sem_nada_parado_usa_a_entrada() -> None:
    modelo = FalhaUmaVez(messages=iter([AIMessage("oi")]))
    agente = create_agent(modelo, tools=[], checkpointer=InMemorySaver())
    contexto = ContextoAgente(
        usuario_id=uuid4(),
        agente_id=uuid4(),
        conversa_id=uuid4(),
        papel="canal",
        thread_proprio=f"canal:{uuid4()}",
    )
    resultado = await rodar_etapa(
        agente, contexto, {"messages": [HumanMessage("oi")]}, continuar_se_parou=True
    )
    assert resultado["messages"][-1].content == "oi"
