"""A linha do tempo só anuncia uma reserva depois de uma resposta real."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.agentes.middleware import montar_middleware
from app.agentes.montagem import ContextoAgente
from app.modelos.enumeracoes import Nivel, TipoProvedor
from app.orquestrador.modelos import modelos_do_papel
from app.preferencias_conversa import EscolhaModelo
from app.seletor.tipos import Capacidade, ContextoSeletor, ModeloCandidato, ProvedorSeletor
from workers.portas import construir_dependencias


class ChatDeTeste(GenericFakeChatModel):
    model_name: str
    ao_responder: Any
    falha: bool = False

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.falha:
            raise httpx.ReadTimeout("O principal não respondeu")
        resposta = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        self.ao_responder("reserva respondeu")
        return resposta


@pytest.mark.parametrize("com_reserva", [False, True])
async def test_modelo_explicito_so_anuncia_reserva_configurada_que_responde(
    monkeypatch, com_reserva
):
    usuario, conversa, agente = uuid4(), uuid4(), uuid4()
    principal = ProvedorSeletor(id=uuid4(), tipo=TipoProvedor.GROQ)
    reserva = ProvedorSeletor(id=uuid4(), tipo=TipoProvedor.OPENAI)
    candidatos = [
        ModeloCandidato(
            modelo=nome,
            provedor=provedor,
            nivel=Nivel.N2,
            capacidades=frozenset({Capacidade.FERRAMENTAS}),
            contexto=8192,
        )
        for nome, provedor in [("groq/principal", principal), ("openai/reserva", reserva)]
    ]
    configuradas = [SimpleNamespace(provedor_id=reserva.id, modelo="openai/reserva")]
    monkeypatch.setattr("app.orquestrador.modelos.modelo_falso_ativo", lambda: False)
    monkeypatch.setattr("app.llm.saude.provedor_falhou", AsyncMock())
    monkeypatch.setattr("app.llm.saude.provedor_respondeu", AsyncMock())
    monkeypatch.setattr(
        "app.seletor.repositorio.contexto_do_usuario",
        AsyncMock(return_value=ContextoSeletor(modelos=candidatos)),
    )
    monkeypatch.setattr("app.seletor.repositorio.config_do_provedor", AsyncMock())
    monkeypatch.setattr("app.core.reservas.configs_extras", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.core.reservas.listar_reservas",
        AsyncMock(return_value=configuradas if com_reserva else []),
    )
    ordem = []

    def fabricar(pares, **_kwargs):
        return [
            ChatDeTeste(
                model_name=nome,
                ao_responder=ordem.append,
                falha=nome == "groq/principal",
                messages=iter([AIMessage("Resposta da reserva")] * 2),
            )
            for nome, _ in pares
        ]

    monkeypatch.setattr("app.llm.fabrica.criar_modelos_na_ordem", fabricar)
    modelos = await modelos_do_papel(
        None,
        usuario,
        "sora",
        escolha=EscolhaModelo(provedor_id=principal.id, modelo="groq/principal"),
    )
    redis = SimpleNamespace(set=AsyncMock(side_effect=[True, None]))

    async def emitir(_redis, passo, *args):
        ordem.append(passo["texto"])

    monkeypatch.setattr("workers.portas._emitir", emitir)
    contexto = ContextoAgente(
        usuario_id=usuario,
        agente_id=agente,
        conversa_id=conversa,
        papel="sora",
        thread_proprio="conversa:pedido:teste",
        dependencias=construir_dependencias(
            {"redis_eventos": redis}, usuario_id=usuario, conversa_id=conversa
        ),
    )
    # O unitário executa só a seleção e a cadeia de middlewares de chamada do modelo.
    chamadas = [
        m
        for m in montar_middleware(contexto, modelos)
        if type(m).__name__ in {"ModelFallbackMiddleware", "ModelRetryMiddleware", "MonitorDeSaude"}
    ]
    grafo = create_agent(modelos[0], middleware=chamadas)
    pedido = {"messages": [{"role": "user", "content": "Responda."}]}
    if not com_reserva:
        assert len(modelos) == 1
        with pytest.raises(httpx.ReadTimeout):
            await grafo.ainvoke(pedido)
        assert ordem == []
        redis.set.assert_not_awaited()
        return

    assert [m.model_name for m in modelos] == ["groq/principal", "openai/reserva"]
    for _ in range(2):
        resposta = await grafo.ainvoke(pedido)
        assert resposta["messages"][-1].content == "Resposta da reserva"
    assert ordem == [
        "reserva respondeu",
        "Continuei com outro modelo de IA.",
        "reserva respondeu",
    ]
