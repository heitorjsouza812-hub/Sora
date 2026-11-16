"""Engrenagem: especialista que responde em texto puro recebe um aviso e volta ao modelo.

Sem ``tool_choice`` o modelo pode responder só com texto; na cadeia isso fazia a etapa falhar com
"o bot terminou sem entregar", jogando fora o trabalho.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agentes.middleware import montar_middleware
from app.agentes.middleware.entrega import MiddlewareExigeEntrega
from app.agentes.montagem import ContextoAgente
from app.llm.falso import criar_modelo_falso


class Roteiro(GenericFakeChatModel):
    chamadas: int = 0

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
        self.chamadas += 1
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


@tool(return_direct=True)
async def entregar(resumo: str) -> str:
    """Entrega o resultado."""
    return "Entregue."


def _entregar() -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"name": "entregar", "args": {"resumo": "ok"}, "id": "c1"}]
    )


async def test_texto_puro_ganha_aviso_e_o_especialista_entrega() -> None:
    modelo = Roteiro(messages=iter([AIMessage("Achei 4 referências..."), _entregar()]))
    agente = create_agent(modelo, tools=[entregar], middleware=[MiddlewareExigeEntrega("entregar")])
    resultado = await agente.ainvoke({"messages": [HumanMessage("pesquise")]})
    assert modelo.chamadas == 2
    assert any(isinstance(m, SystemMessage) for m in resultado["messages"])
    assert isinstance(resultado["messages"][-1], ToolMessage)


async def test_aviso_so_uma_vez_por_execucao() -> None:
    modelo = Roteiro(messages=iter([AIMessage("a"), AIMessage("b"), AIMessage("c")]))
    agente = create_agent(modelo, tools=[entregar], middleware=[MiddlewareExigeEntrega("entregar")])
    await agente.ainvoke({"messages": [HumanMessage("pesquise")]})
    assert modelo.chamadas == 2


def test_so_os_especialistas_da_cadeia_recebem_o_aviso() -> None:
    def tem(papel: str) -> list[str]:
        contexto = ContextoAgente(
            usuario_id=uuid4(),
            agente_id=uuid4(),
            conversa_id=uuid4(),
            papel=papel,  # type: ignore[arg-type]
        )
        return [
            m.ferramenta
            for m in montar_middleware(contexto, [criar_modelo_falso(papel)])
            if isinstance(m, MiddlewareExigeEntrega)
        ]

    assert tem("pesquisador") == ["entregar"]
    assert tem("verificador") == ["veredito"]
    assert tem("individual") == []
    assert tem("sora") == []
