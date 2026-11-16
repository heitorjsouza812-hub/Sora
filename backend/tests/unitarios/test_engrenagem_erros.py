"""Engrenagem: erros no ciclo tool_use → tool_result.

- exceção inesperada dentro de uma ferramenta volta ao modelo (sem detalhe interno) em vez de
  derrubar o turno; cancelamento e ``falar`` continuam parando;
- argumentos que não são JSON (``invalid_tool_calls``) fazem a chamada ao modelo ser repetida,
  em vez de o turno acabar mudo;
- nome de ferramenta inexistente e argumento fora do esquema voltam ao modelo como erro.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agentes.middleware.cancelamento import CadeiaCancelada
from app.agentes.middleware.conserto_json import middleware_de_conserto
from app.agentes.middleware.limite_provedor import MiddlewareLimiteDoProvedor


class Roteiro(GenericFakeChatModel):
    chamadas: int = 0

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
        self.chamadas += 1
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _ai(nome: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": nome, "args": args, "id": "c1"}])


class Texto(BaseModel):
    texto: str = Field(min_length=1)


@tool
async def rede(endereco: str) -> str:
    """Busca algo na rede."""
    raise ConnectionError("10.0.0.5:5432 recusou a conexão")  # detalhe interno


@tool
async def cancelada(x: str) -> str:
    """Cancelada no meio."""
    raise CadeiaCancelada("parou")


@tool(args_schema=Texto)
async def falar(texto: str) -> str:
    """Fala."""
    raise RuntimeError("redis caiu depois de gravar")


def _agente(roteiro: list[AIMessage], *middleware: Any):  # type: ignore[no-untyped-def]
    modelo = Roteiro(messages=iter(roteiro))
    agente = create_agent(
        modelo,
        tools=[rede, cancelada, falar],
        middleware=[*middleware, middleware_de_conserto()],
    )
    return agente, modelo


async def test_excecao_inesperada_na_ferramenta_volta_ao_modelo_sem_detalhe() -> None:
    agente, _ = _agente([_ai("rede", {"endereco": "x"}), AIMessage("segui sem a rede")])
    resultado = await agente.ainvoke({"messages": [HumanMessage("oi")]})
    erro = next(m for m in resultado["messages"] if isinstance(m, ToolMessage))
    assert erro.status == "error"
    assert "ConnectionError" in erro.content
    assert "10.0.0.5" not in erro.content
    assert resultado["messages"][-1].content == "segui sem a rede"


async def test_cancelamento_e_falar_continuam_parando_o_turno() -> None:
    agente, _ = _agente([_ai("cancelada", {"x": "a"}), AIMessage("não")])
    with pytest.raises(CadeiaCancelada):
        await agente.ainvoke({"messages": [HumanMessage("oi")]})
    agente, _ = _agente([_ai("falar", {"texto": "oi"}), AIMessage("não")])
    with pytest.raises(RuntimeError):
        await agente.ainvoke({"messages": [HumanMessage("oi")]})


async def test_nome_inexistente_e_argumento_invalido_voltam_ao_modelo() -> None:
    agente, _ = _agente(
        [
            _ai("conectar_buscar_ferramentas", {}),
            _ai("falar", {"texto": ""}),
            AIMessage("fim"),
        ]
    )
    resultado = await agente.ainvoke({"messages": [HumanMessage("oi")]})
    erros = [m for m in resultado["messages"] if isinstance(m, ToolMessage)]
    assert [m.status for m in erros] == ["error", "error"]
    assert "not a valid tool" in erros[0].content
    assert "texto" in erros[1].content


async def test_argumentos_que_nao_sao_json_repetem_a_chamada_ao_modelo() -> None:
    quebrada = AIMessage(
        content="",
        invalid_tool_calls=[{"name": "rede", "args": '{"endereco": "x', "id": "c1", "error": None}],
    )
    agente, modelo = _agente([quebrada, AIMessage("respondi")], MiddlewareLimiteDoProvedor())
    resultado = await agente.ainvoke({"messages": [HumanMessage("oi")]})
    assert modelo.chamadas == 2
    assert resultado["messages"][-1].content == "respondi"


async def test_json_quebrado_que_persiste_nao_vira_laco() -> None:
    quebrada = AIMessage(
        content="",
        invalid_tool_calls=[{"name": "rede", "args": "{", "id": "c1", "error": None}],
    )
    agente, modelo = _agente([quebrada] * 5, MiddlewareLimiteDoProvedor())
    await agente.ainvoke({"messages": [HumanMessage("oi")]})
    assert modelo.chamadas == 3  # a primeira e mais duas tentativas
