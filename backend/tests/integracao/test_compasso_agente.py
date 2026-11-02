"""Caminho do agente de verdade em ``executar_etapa`` (Postgres e Redis reais, modelo falso).

Prova: (1) ``entregar`` grava a entrega e o worker não grava de novo; (2) ``perguntar``
pausa a etapa (``__interrupt__``) e a retomada com a resposta conclui; (3) o middleware de
mensagens pendentes está ligado pelo worker.
"""

# ruff: noqa: F401, F811
from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.banco import fabrica_sessoes
from app.eventos.streams import canal_conversa
from app.ferramentas import ambiente
from app.ferramentas.entregar import Entregar
from app.ferramentas.perguntar import Opcao, Perguntar
from app.llm.falso import classe_modelo_falso
from app.modelos.enumeracoes import StatusCadeia, StatusEtapa, TipoProvedor
from app.modelos.tabelas import Cadeia, Entrega, Etapa, ModeloDisponivel, Provedor, Usuario
from tests.integracao.test_fase_b_pronto import (
    SENHA,
    ambiente_fase_b,
    servicos_fase_b,
)
from workers.cadeia import dependencias_da_etapa, executar_etapa, planejar_cadeia

pytestmark = pytest.mark.integracao


def _chamada(nome: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": nome, "args": args, "id": f"t_{nome}", "type": "tool_call"}],
    )


def _entregar() -> AIMessage:
    args = Entregar(tipo="texto", titulo="Texto", resumo="1 texto", conteudo="Olá").model_dump(
        mode="json"
    )
    return _chamada("entregar", args)


def _perguntar() -> AIMessage:
    args = Perguntar(
        texto="Qual tom?",
        opcoes=[Opcao(rotulo="Formal", valor="formal"), Opcao(rotulo="Leve", valor="leve")],
    ).model_dump(mode="json")
    return _chamada("perguntar", args)


def _modelo_roteirizado(roteiro: list[AIMessage], vistos: list[str] | None = None):
    base = classe_modelo_falso()

    class Roteirizado(base):  # type: ignore[valid-type, misc]
        def _generate(self, messages, *args, **kwargs):
            if vistos is not None:
                vistos.extend(str(m.content) for m in messages)
            return super()._generate(messages, *args, **kwargs)

    return Roteirizado(messages=iter(roteiro), papel="pesquisador", model_name="falso/roteiro")


async def _preparar(cliente, fabrica, email: str):
    await cliente.post(
        "/v1/auth/cadastrar",
        json={"nome": "Ana", "email": email, "senha": SENHA, "convite": "FASE-B"},
    )
    login = await cliente.post("/v1/auth/entrar", json={"email": email, "senha": SENHA})
    auth = {"Authorization": f"Bearer {login.json()['token_acesso']}"}
    async with fabrica() as sessao:
        usuario = await sessao.scalar(select(Usuario).where(Usuario.email == email))
        provedor = Provedor(usuario_id=usuario.id, tipo=TipoProvedor.GROQ)
        sessao.add(provedor)
        await sessao.flush()
        sessao.add(
            ModeloDisponivel(
                provedor_id=provedor.id,
                modelo="groq/openai/gpt-oss-20b",
                nivel="N1",
                capacidades=["ferramentas", "json"],
                contexto=131_072,
                velocidade_tps=100,
            )
        )
        await sessao.commit()
    resposta = await cliente.post(
        "/v1/conversas", headers=auth, json={"texto": "crie uma campanha", "anexos": []}
    )
    conversa_id = resposta.json()["id"]
    async with fabrica() as sessao:
        cadeia = await sessao.scalar(select(Cadeia).where(Cadeia.conversa_id == conversa_id))
        cadeia_id = cadeia.id
    return conversa_id, cadeia_id


async def _etapa1(fabrica, cadeia_id):
    async with fabrica() as sessao:
        return await sessao.scalar(
            select(Etapa).where(Etapa.cadeia_id == cadeia_id).order_by(Etapa.ordem).limit(1)
        )


def _limpar_caches() -> None:
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()


async def test_entregar_nao_duplica_e_pergunta_pausa_e_retoma(
    ambiente_fase_b: tuple[Any, async_sessionmaker, Any],
) -> None:
    _limpar_caches()
    cliente, fabrica, redis = ambiente_fase_b
    conversa_id, cadeia_id = await _preparar(cliente, fabrica, "agente-a@exemplo.com")
    ctx: dict[str, Any] = {"sessoes": fabrica, "redis_eventos": redis}
    await planejar_cadeia(ctx, str(cadeia_id))
    etapa = await _etapa1(fabrica, cadeia_id)

    vistos0: list[str] = []
    modelo = _modelo_roteirizado([_perguntar(), _entregar()], vistos0)
    ctx["checkpointer"] = InMemorySaver()
    ctx["modelos_da_etapa"] = lambda papel: [modelo]

    # (2) pausa na pergunta
    await executar_etapa(ctx, str(etapa.id))
    async with fabrica() as sessao:
        etapa_pausada = await sessao.get(Etapa, etapa.id)
        cadeia = await sessao.get(Cadeia, cadeia_id)
        assert etapa_pausada.status == StatusEtapa.AGUARDANDO_USUARIO
        assert cadeia.status == StatusCadeia.AGUARDANDO_USUARIO
        assert await sessao.scalar(select(func.count()).select_from(Entrega)) == 0
    nomes = [c["event"] for _, c in await redis.xrange(canal_conversa(conversa_id))]
    assert nomes.count("pergunta") == 1

    # retoma com a resposta: conclui, uma única entrega, um único evento
    await executar_etapa(ctx, str(etapa.id), resposta={"pergunta_id": "p", "valor": "leve"})
    async with fabrica() as sessao:
        concluida = await sessao.get(Etapa, etapa.id)
        cadeia = await sessao.get(Cadeia, cadeia_id)
        assert concluida.status == StatusEtapa.CONCLUIDA
        assert cadeia.status == StatusCadeia.EXECUTANDO
        entregas = (await sessao.scalars(select(Entrega).where(Entrega.etapa_id == etapa.id))).all()
        assert len(entregas) == 1  # (1) o worker não gravou de novo
        assert concluida.saida["entrega_id"] == str(entregas[0].id)
    eventos = [
        (c["event"], json.loads(c["data"]))
        for _, c in await redis.xrange(canal_conversa(conversa_id))
    ]
    assert [n for n, _ in eventos].count("entrega") == 1

    # resposta repetida não roda de novo
    await executar_etapa(ctx, str(etapa.id), resposta={"pergunta_id": "p", "valor": "leve"})
    async with fabrica() as sessao:
        assert await sessao.scalar(select(func.count()).select_from(Entrega)) == 1

    # (3) mensagens pendentes: a porta do worker esta ligada e o modelo recebe a correcao
    assert dependencias_da_etapa().ler_mensagens_pendentes is ambiente.ler_mensagens_pendentes
    async with fabrica() as sessao:
        etapa2 = await sessao.scalar(
            select(Etapa).where(Etapa.cadeia_id == cadeia_id, Etapa.ordem == 2)
        )
    await ambiente.guardar_mensagem(etapa2.id, "mude o foco para o publico jovem")
    vistos: list[str] = []
    modelo2 = _modelo_roteirizado([_entregar()], vistos)
    ctx["modelos_da_etapa"] = lambda papel: [modelo2]
    await executar_etapa(ctx, str(etapa2.id))
    assert any("<mensagem_da_sora>mude o foco para o publico jovem" in t for t in vistos)
    assert await ambiente.ler_mensagens_pendentes(etapa2.id) == []
