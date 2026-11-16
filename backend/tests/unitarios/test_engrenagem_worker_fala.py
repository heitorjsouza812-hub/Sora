"""Engrenagem: o worker só fala por conta própria o texto puro com que ESTE turno terminou.

Antes ele voltava pelo histórico inteiro: um turno sem texto final (resposta vazia, retomada
depois de um cartão) achava a resposta de um turno anterior e a mandava de novo (duplicada).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import workers.conversa as conversa
from workers.conversa import _texto_da_resposta


def _chamada(nome: str, args: dict[str, Any], id_: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": nome, "args": args, "id": id_}])


def test_texto_puro_no_fim_do_turno_e_falado() -> None:
    resultado = {"messages": [HumanMessage("oi"), AIMessage("Olá!")]}
    assert _texto_da_resposta(resultado) == "Olá!"


def test_resposta_de_turno_anterior_nao_e_repetida() -> None:
    resultado = {
        "messages": [
            HumanMessage("primeira"),
            AIMessage("Resposta antiga."),
            HumanMessage("segunda"),
            _chamada("buscar_web", {"consulta": "x"}, "c1"),
            ToolMessage("nada", tool_call_id="c1", name="buscar_web"),
            AIMessage(""),  # o modelo terminou sem texto
        ]
    }
    assert _texto_da_resposta(resultado) == ""


def test_retomada_que_terminou_com_falar_nao_repete_nada() -> None:
    resultado = {
        "messages": [
            HumanMessage("abre o excel"),
            AIMessage("Vou abrir o Excel.", tool_calls=[{"name": "falar", "args": {}, "id": "c1"}]),
            ToolMessage("Mensagem enviada ao usuário.", tool_call_id="c1", name="falar"),
            _chamada("computador_agir", {}, "c2"),
            ToolMessage("feito", tool_call_id="c2", name="computador_agir"),
            _chamada("falar", {"texto": "Abri."}, "c3"),
            ToolMessage("Mensagem enviada ao usuário.", tool_call_id="c3", name="falar"),
        ]
    }
    assert _texto_da_resposta(resultado) == ""


def test_texto_em_blocos_tambem_conta() -> None:
    final = AIMessage(content=[{"type": "text", "text": "Oi "}, {"type": "text", "text": "ali"}])
    assert _texto_da_resposta({"messages": [HumanMessage("x"), final]}) == "Oi\nali"


class _Sessao:
    def __init__(self, contagens: list[int]) -> None:
        self._contagens = contagens

    async def scalar(self, _consulta: Any) -> int:
        return self._contagens.pop(0)


@pytest.mark.parametrize(
    ("resultado_final", "contagens", "falas_esperadas"),
    [
        # retomada: o turno já falou (3 → 4 mensagens) e terminou com texto puro: não repete
        (AIMessage("Pronto, abri."), [3, 4], 0),
        # retomada sem fala nenhuma: o texto puro do fim é falado
        (AIMessage("Pronto, abri."), [3, 3], 1),
    ],
)
async def test_retomada_conta_as_mensagens_antes_de_rodar(
    monkeypatch: pytest.MonkeyPatch,
    resultado_final: AIMessage,
    contagens: list[int],
    falas_esperadas: int,
) -> None:
    falas: list[str] = []

    @asynccontextmanager
    async def sessoes():  # type: ignore[no-untyped-def]
        yield _Sessao(contagens)

    async def montar_e_rodar_agente(**_: Any) -> dict[str, Any]:
        return {"messages": [HumanMessage("pedido"), AIMessage("antiga"), resultado_final]}

    async def falar(args: Any, _contexto: Any) -> str:
        falas.append(args.texto)
        return "ok"

    async def publicar(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr("app.agentes.montar_e_rodar_agente", montar_e_rodar_agente)
    monkeypatch.setattr("app.ferramentas.falar.falar", falar)
    monkeypatch.setattr(conversa, "publicar_evento", publicar)
    from types import SimpleNamespace

    contexto = SimpleNamespace(
        usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4(), papel="individual"
    )
    ctx = {"sessoes": sessoes, "checkpointer": None, "redis_eventos": None}
    await conversa._rodar_e_falar(ctx, contexto, [], antes=None, resposta={"decisao": "x"})
    assert len(falas) == falas_esperadas


async def test_item_sem_mensagem_roda_em_thread_propria(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repetir: o item roda numa thread só dele, não na thread da conversa (onde cada execução
    acrescentava o histórico inteiro de novo)."""
    from types import SimpleNamespace

    capturado: dict[str, Any] = {}

    async def responder(ctx: Any, mensagem_id: Any, **kwargs: Any) -> None:
        capturado.update(kwargs, mensagem_id=mensagem_id)

    monkeypatch.setattr(conversa, "_responder_direto_sem_fila", responder)
    item = SimpleNamespace(
        id=uuid4(), chave=None, agente_id=uuid4(), usuario_id=uuid4(), texto="de novo", anexos=[]
    )
    await conversa.rodar_turno_do_item({}, item)
    assert capturado["mensagem_id"] is None
    assert capturado["item_id"] == item.id
