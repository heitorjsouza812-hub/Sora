"""Engrenagem: a mesma fala não sai duas vezes no turno (resposta duplicada do bot)."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agentes.middleware.encerra_depois_de_falar import (
    MiddlewareEncerraDepoisDeFalar,
    deve_encerrar,
)
from app.agentes.middleware.fala_unica import JA_ENVIADA, MiddlewareFalaUnica, fala_repetida


class Roteiro(GenericFakeChatModel):
    """Responde na ordem do roteiro e conta as chamadas."""

    chamadas: int = 0

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
        self.chamadas += 1
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _ai(*chamadas: tuple[str, dict[str, Any], str], texto: str = "") -> AIMessage:
    return AIMessage(
        content=texto,
        tool_calls=[{"name": n, "args": a, "id": i, "type": "tool_call"} for n, a, i in chamadas],
    )


def _agente(roteiro: list[AIMessage], falados: list[str]):  # type: ignore[no-untyped-def]
    class Args(BaseModel):
        texto: str = Field(min_length=1)

    @tool(args_schema=Args)
    async def falar(texto: str) -> str:
        """Fala com o usuário."""
        falados.append(texto)
        return "Mensagem enviada ao usuário."

    @tool
    async def lembrar(fato: str) -> str:
        """Guarda um fato."""
        return "Guardei."

    modelo = Roteiro(messages=iter(roteiro))
    agente = create_agent(
        modelo,
        tools=[falar, lembrar],
        middleware=[MiddlewareEncerraDepoisDeFalar(), MiddlewareFalaUnica()],
    )
    return agente, modelo


async def test_resposta_repetida_na_chamada_seguinte_nao_sai_de_novo_e_o_turno_acaba() -> None:
    # Pedido simples: a 1ª ação (falar) já é a resposta; o modelo é chamado de novo e repete.
    falados: list[str] = []
    agente, modelo = _agente(
        [
            _ai(("falar", {"texto": "A capital é Brasília."}, "c1")),
            _ai(("falar", {"texto": "  a capital é   Brasília. "}, "c2")),
            AIMessage("não devia chegar aqui"),
        ],
        falados,
    )
    resultado = await agente.ainvoke({"messages": [HumanMessage("qual a capital?")]})
    assert falados == ["A capital é Brasília."]
    assert modelo.chamadas == 2  # a repetição encerra o turno: sem 3ª chamada ao modelo
    ultima = resultado["messages"][-1]
    assert isinstance(ultima, ToolMessage) and ultima.content == JA_ENVIADA


async def test_duas_chamadas_falar_iguais_na_mesma_resposta_saem_uma_vez() -> None:
    falados: list[str] = []
    agente, _ = _agente(
        [
            _ai(("falar", {"texto": "Oi!"}, "c1"), ("falar", {"texto": "Oi!"}, "c2")),
            AIMessage(""),
        ],
        falados,
    )
    await agente.ainvoke({"messages": [HumanMessage("oi")]})
    assert falados == ["Oi!"]


async def test_falas_diferentes_e_mesma_fala_em_outro_turno_continuam_saindo() -> None:
    falados: list[str] = []
    agente, _ = _agente(
        [
            _ai(("falar", {"texto": "Vou guardar."}, "c1")),
            _ai(("lembrar", {"fato": "x"}, "c2")),
            _ai(("falar", {"texto": "Guardei."}, "c3")),
        ],
        falados,
    )
    historico = [HumanMessage("antes"), AIMessage("Vou guardar.")]
    await agente.ainvoke({"messages": [*historico, HumanMessage("guarda x")]})
    assert falados == ["Vou guardar.", "Guardei."]


def test_fala_que_deu_erro_pode_ser_repetida() -> None:
    mensagens = [
        HumanMessage("oi"),
        _ai(("falar", {"texto": "Oi"}, "c1")),
        ToolMessage("Erro: anexo", tool_call_id="c1", name="falar", status="error"),
        _ai(("falar", {"texto": "Oi"}, "c2")),
    ]
    assert not fala_repetida(mensagens, mensagens[-1].tool_calls[0])


def test_deve_encerrar_depois_da_fala_repetida_mesmo_sendo_o_primeiro_passo() -> None:
    mensagens = [
        HumanMessage("oi"),
        _ai(("falar", {"texto": "Oi"}, "c1"), ("falar", {"texto": "Oi"}, "c2")),
        ToolMessage("Mensagem enviada ao usuário.", tool_call_id="c1", name="falar"),
        ToolMessage(JA_ENVIADA, tool_call_id="c2", name="falar"),
    ]
    assert deve_encerrar(mensagens)
