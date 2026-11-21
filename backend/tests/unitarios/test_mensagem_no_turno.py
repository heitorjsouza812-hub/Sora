""" "Mandar agora": a mensagem do usuário entra no turno em andamento (Onda 2).

Sem banco: o middleware com um agente de verdade (modelo falso) e o fechamento do turno, que
manda pela fila normal o que sobrou no correio. A entrega atômica no Redis (script Lua) e a rota
estão em ``tests/integracao/test_mensagem_no_turno.py``.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from pydantic import Field

from app.agentes.middleware.mensagens import PREFIXO_MENSAGEM_NO_TURNO, MiddlewareMensagemNoTurno


class Modelo(GenericFakeChatModel):
    recebidas: list[list[Any]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
        self.recebidas.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


async def test_mensagem_chega_entre_duas_chamadas_do_modelo() -> None:
    conversa = uuid4()
    correio: list[str] = []

    @tool
    async def pesquisar(tema: str) -> str:
        """Pesquisa um tema."""
        correio.append("Na verdade, use a cor azul.")  # o usuário manda no meio do turno
        return "achei três referências"

    async def ler(conversa_id: Any) -> list[str]:
        assert conversa_id == conversa
        lidas = list(correio)
        correio.clear()
        return lidas

    modelo = Modelo(
        messages=iter(
            [
                AIMessage("", tool_calls=[{"name": "pesquisar", "args": {"tema": "x"}, "id": "1"}]),
                AIMessage("Pronto, em azul."),
            ]
        )
    )
    agente = create_agent(
        modelo, tools=[pesquisar], middleware=[MiddlewareMensagemNoTurno(conversa, ler=ler)]
    )
    resultado = await agente.ainvoke({"messages": [HumanMessage("Crie o logo.")]})

    primeira, segunda = modelo.recebidas
    assert not any(PREFIXO_MENSAGEM_NO_TURNO in str(m.content) for m in primeira)
    injetada = [m for m in segunda if PREFIXO_MENSAGEM_NO_TURNO in str(m.content)]
    assert len(injetada) == 1 and isinstance(injetada[0], HumanMessage)
    assert "use a cor azul" in str(injetada[0].content)
    # fica no estado do turno (o histórico salvo leva a mensagem)
    assert any("use a cor azul" in str(m.content) for m in resultado["messages"])


async def test_sem_mensagem_nao_muda_nada() -> None:
    async def ler(_conversa_id: Any) -> list[str]:
        return []

    modelo = Modelo(messages=iter([AIMessage("ok")]))
    agente = create_agent(modelo, middleware=[MiddlewareMensagemNoTurno(uuid4(), ler=ler)])
    resultado = await agente.ainvoke({"messages": [HumanMessage("oi")]})
    assert [type(m).__name__ for m in resultado["messages"]] == ["HumanMessage", "AIMessage"]


async def test_fechar_turno_manda_as_sobras_pela_fila_normal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ferramentas import ambiente
    from workers import conversa as worker

    chamadas: list[tuple[str, Any]] = []

    async def desmarcar(conversa_id: Any, marca: str, redis: Any = None) -> None:
        chamadas.append(("desmarcar", marca))

    async def esvaziar(_conversa_id: Any, redis: Any = None) -> list[dict[str, str]]:
        return [{"mensagem_id": "m1", "texto": "chegou tarde"}, {"mensagem_id": "", "texto": "x"}]

    async def enfileirar(job: str, **args: Any) -> None:
        chamadas.append((job, args))

    monkeypatch.setattr(ambiente, "desmarcar_turno_vivo", desmarcar)
    monkeypatch.setattr(ambiente, "esvaziar_correio_do_turno", esvaziar)
    monkeypatch.setattr("workers.fila.enfileirar", enfileirar)
    await worker._fechar_turno_vivo(uuid4(), "marca-1")
    assert chamadas == [
        ("desmarcar", "marca-1"),
        ("responder_direto", {"id_job": "responder:m1", "mensagem_id": "m1"}),
    ]
    chamadas.clear()
    await worker._fechar_turno_vivo(uuid4(), None)  # o turno nem chegou a ser marcado
    assert chamadas == []
