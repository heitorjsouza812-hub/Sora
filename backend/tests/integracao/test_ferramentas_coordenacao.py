"""Ferramentas de coordenação com Postgres e Redis reais (Docker); sem Docker, pula."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typing_extensions import TypedDict

from app.core.banco import fabrica_sessoes
from app.core.config import obter_configuracao
from app.eventos.streams import canal_conversa
from app.ferramentas import ambiente
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.criar_agente import CriarAgente, criar_agente
from app.ferramentas.disparar_especialista import DispararEspecialista, disparar_especialista
from app.ferramentas.entregar import Entregar, entregar
from app.ferramentas.mensagem_especialista import MensagemEspecialista, mensagem_especialista
from app.ferramentas.parar_especialista import PararEspecialista, parar_especialista
from app.ferramentas.perguntar import Opcao, Perguntar, perguntar
from app.ferramentas.ver_especialista import VerEspecialista, ver_especialista
from app.ferramentas.veredito import RequisitoVerificado, Veredito, veredito
from app.modelos.enumeracoes import AutorMensagem, StatusEtapa, TipoAgente
from app.modelos.tabelas import (
    Agente,
    Cadeia,
    Conversa,
    Entrega,
    Etapa,
    Mensagem,
    Pergunta,
    Usuario,
)

pytestmark = pytest.mark.integracao

RAIZ = Path(__file__).resolve().parents[2]


class Cenario:
    usuario_id: UUID
    sora_id: UUID
    conversa_id: UUID
    cadeia_id: UUID
    redis: Redis

    def contexto(self, etapa_id: UUID | None = None) -> ContextoFerramenta:
        return ContextoFerramenta(
            usuario_id=self.usuario_id,
            agente_id=self.sora_id,
            conversa_id=self.conversa_id,
            cadeia_id=self.cadeia_id,
            etapa_id=etapa_id,
        )


@pytest.fixture(scope="module")
def servicos():
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    with (
        PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg") as postgres,
        RedisContainer("redis:7") as redis,
    ):
        yield (
            postgres.get_connection_url(),
            f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0",
        )


@pytest.fixture
async def cenario(servicos, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Cenario]:
    url_pg, url_redis = servicos
    monkeypatch.setenv("AMBIENTE", "teste")
    monkeypatch.setenv("DATABASE_URL", url_pg)
    monkeypatch.setenv("REDIS_URL", url_redis)
    obter_configuracao.cache_clear()
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()

    alembic = Config(str(RAIZ / "alembic.ini"))
    alembic.set_main_option("script_location", str(RAIZ / "migrations"))
    await asyncio.to_thread(command.upgrade, alembic, "head")

    c = Cenario()
    c.redis = Redis.from_url(url_redis, decode_responses=True)
    await c.redis.flushdb()
    motor = create_async_engine(url_pg)
    async with async_sessionmaker(motor, expire_on_commit=False)() as sessao:
        usuario = Usuario(email=f"{uuid4()}@exemplo.com", nome="Ana", senha_hash="x")
        sessao.add(usuario)
        await sessao.flush()
        sora = Agente(usuario_id=usuario.id, tipo=TipoAgente.SORA, nome="Sora")
        sessao.add(sora)
        await sessao.flush()
        conversa = Conversa(usuario_id=usuario.id, agente_id=sora.id)
        sessao.add(conversa)
        await sessao.flush()
        pedido = Mensagem(conversa_id=conversa.id, autor=AutorMensagem.USUARIO, conteudo="oi")
        sessao.add(pedido)
        await sessao.flush()
        cadeia = Cadeia(
            usuario_id=usuario.id,
            conversa_id=conversa.id,
            pedido_id=pedido.id,
            orcamento_tokens=100_000,
        )
        sessao.add(cadeia)
        await sessao.commit()
        c.usuario_id, c.sora_id = usuario.id, sora.id
        c.conversa_id, c.cadeia_id = conversa.id, cadeia.id
    yield c
    await c.redis.aclose()
    await ambiente.redis_dos_eventos().aclose()
    await motor.dispose()
    ambiente.redis_dos_eventos.cache_clear()
    fabrica_sessoes.cache_clear()
    obter_configuracao.cache_clear()


async def _eventos(c: Cenario) -> list[str]:
    itens = await c.redis.xrange(canal_conversa(c.conversa_id))
    return [campos["event"] for _, campos in itens]


async def _disparar(c: Cenario, tarefa: str = "pesquisar cafeterias") -> UUID:
    return UUID(
        await disparar_especialista(
            DispararEspecialista(papel="pesquisador", tarefa=tarefa), c.contexto()
        )
    )


@pytest.fixture
def fila(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    chamadas: list[tuple[str, dict[str, Any]]] = []

    async def falsa(job: str, **args: Any) -> None:
        chamadas.append((job, args))

    monkeypatch.setattr("workers.fila.enfileirar", falsa)
    return chamadas


async def test_disparar_cria_etapa_enfileira_e_reaproveita(cenario: Cenario, fila) -> None:
    etapa_id = await _disparar(cenario)
    assert await _disparar(cenario) == etapa_id  # mesma tarefa, ainda ativa
    segunda = await _disparar(cenario, "outra tarefa")
    assert segunda != etapa_id
    assert [c[0] for c in fila] == ["executar_etapa", "executar_etapa"]
    assert fila[0][1] == {"etapa_id": str(etapa_id)}
    async with fabrica_sessoes()() as sessao:
        etapas = (await sessao.scalars(select(Etapa).order_by(Etapa.ordem))).all()
    assert [e.ordem for e in etapas] == [1, 2]
    assert etapas[0].nivel == "N2" and etapas[0].status == StatusEtapa.PENDENTE


async def test_disparar_sem_cadeia_e_erro(cenario: Cenario, fila) -> None:
    contexto = ContextoFerramenta(
        usuario_id=cenario.usuario_id, agente_id=cenario.sora_id, conversa_id=cenario.conversa_id
    )
    with pytest.raises(ErroFerramenta):
        await disparar_especialista(DispararEspecialista(papel="redator", tarefa="x"), contexto)


async def test_entregar_e_idempotente_e_emite_um_evento(cenario: Cenario, fila) -> None:
    etapa_id = await _disparar(cenario)
    contexto = cenario.contexto(etapa_id=etapa_id)
    args = Entregar(tipo="links", titulo="Pesquisa", resumo="4 referências", conteudo=["a", "b"])
    await entregar(args, contexto)
    await entregar(args.model_copy(update={"resumo": "5 referências"}), contexto)
    async with fabrica_sessoes()() as sessao:
        linhas = (await sessao.scalars(select(Entrega))).all()
    assert len(linhas) == 1
    assert linhas[0].resumo == "5 referências" and linhas[0].versao == 1
    assert linhas[0].conteudo["dados"] == ["a", "b"]
    assert (await _eventos(cenario)).count("entrega") == 1


async def test_veredito_grava_na_etapa(cenario: Cenario, fila) -> None:
    etapa_id = await _disparar(cenario)
    v = Veredito(
        aprovado=False,
        requisitos=[RequisitoVerificado(requisito="r", evidencia="e", status="parcial")],
        motivo="faltou fonte",
    )
    texto = await veredito(v, cenario.contexto(etapa_id=etapa_id))
    assert "reprovado" in texto
    async with fabrica_sessoes()() as sessao:
        etapa = await sessao.get(Etapa, etapa_id)
    assert etapa.saida["veredito"]["motivo"] == "faltou fonte"


async def test_ver_mensagem_e_parar_especialista(cenario: Cenario, fila) -> None:
    etapa_id = await _disparar(cenario)
    contexto = cenario.contexto()
    assert "pendente" in await ver_especialista(VerEspecialista(etapa_id=etapa_id), contexto)

    mensagem = MensagemEspecialista(etapa_id=etapa_id, texto="foque em SP")
    await mensagem_especialista(mensagem, contexto)
    assert await ambiente.ler_mensagens_pendentes(etapa_id) == ["foque em SP"]
    assert await ambiente.ler_mensagens_pendentes(etapa_id) == []  # esvaziou

    await parar_especialista(PararEspecialista(etapa_id=etapa_id), contexto)
    assert "cancelada" in await ver_especialista(VerEspecialista(etapa_id=etapa_id), contexto)
    assert "já estava" in await parar_especialista(PararEspecialista(etapa_id=etapa_id), contexto)
    with pytest.raises(ErroFerramenta):  # etapa terminou
        await mensagem_especialista(mensagem, contexto)


async def test_etapa_de_outro_usuario_e_nao_encontrada(cenario: Cenario, fila) -> None:
    etapa_id = await _disparar(cenario)
    intruso = ContextoFerramenta(
        usuario_id=uuid4(),
        agente_id=cenario.sora_id,
        conversa_id=cenario.conversa_id,
        cadeia_id=cenario.cadeia_id,
    )
    with pytest.raises(ErroFerramenta):
        await ver_especialista(VerEspecialista(etapa_id=etapa_id), intruso)
    with pytest.raises(ErroFerramenta):
        await parar_especialista(PararEspecialista(etapa_id=etapa_id), intruso)


class _Estado(TypedDict, total=False):
    resultado: str


def _grafo(funcao) -> Any:
    """Um nó que chama a ferramenta, para provar interrupção e retomada de verdade."""

    async def no(_: _Estado) -> _Estado:
        return {"resultado": await funcao()}

    montado = StateGraph(_Estado)
    montado.add_node("no", no)
    montado.add_edge(START, "no")
    montado.add_edge("no", END)
    return montado.compile(checkpointer=MemorySaver())


async def test_perguntar_interrompe_grava_uma_vez_e_retoma(cenario: Cenario) -> None:
    pergunta = Perguntar(
        texto="Qual tom?",
        opcoes=[Opcao(rotulo="Formal", valor="formal"), Opcao(rotulo="Leve", valor="leve")],
    )
    grafo = _grafo(lambda: perguntar(pergunta, cenario.contexto()))
    config = {"configurable": {"thread_id": "t1"}}
    interrompido = await grafo.ainvoke({}, config=config)
    assert "__interrupt__" in interrompido
    final = await grafo.ainvoke(Command(resume="leve"), config=config)
    assert final["resultado"] == "leve"
    async with fabrica_sessoes()() as sessao:
        assert len((await sessao.scalars(select(Pergunta))).all()) == 1
    assert (await _eventos(cenario)).count("pergunta") == 1


async def test_criar_agente_pede_cartao_aprovado_cria_uma_vez(cenario: Cenario) -> None:
    args = CriarAgente(nome="Teo", papel="Responde e-mails de clientes")
    grafo = _grafo(lambda: criar_agente(args, cenario.contexto()))
    config = {"configurable": {"thread_id": "t2"}}
    assert "__interrupt__" in await grafo.ainvoke({}, config=config)
    assert "aprovacao.pedida" in await _eventos(cenario)
    final = await grafo.ainvoke(Command(resume="permitir_uma_vez"), config=config)
    assert "criado" in final["resultado"]
    async with fabrica_sessoes()() as sessao:
        individuais = (
            await sessao.scalars(select(Agente).where(Agente.tipo == TipoAgente.INDIVIDUAL))
        ).all()
    assert [a.nome for a in individuais] == ["Teo"]
    assert individuais[0].cor.upper() != "#E2ECFF"
    assert (await _eventos(cenario)).count("agente.criado") == 1


async def test_criar_agente_negado_nao_cria(cenario: Cenario) -> None:
    args = CriarAgente(nome="Lia", papel="Faz resumos")
    grafo = _grafo(lambda: criar_agente(args, cenario.contexto()))
    config = {"configurable": {"thread_id": "t3"}}
    await grafo.ainvoke({}, config=config)
    final = await grafo.ainvoke(Command(resume="negar"), config=config)
    assert "não aprovou" in final["resultado"]
    async with fabrica_sessoes()() as sessao:
        nomes = (
            await sessao.scalars(select(Agente.nome).where(Agente.tipo == TipoAgente.INDIVIDUAL))
        ).all()
    assert "Lia" not in nomes


async def test_criar_agente_respeita_limite_de_cinco(cenario: Cenario) -> None:
    async with fabrica_sessoes()() as sessao:
        for i in range(5):
            sessao.add(
                Agente(
                    usuario_id=cenario.usuario_id,
                    tipo=TipoAgente.INDIVIDUAL,
                    nome=f"A{i}",
                    papel=f"p{i}",
                )
            )
        await sessao.commit()
    with pytest.raises(ErroFerramenta, match="Limite"):
        await criar_agente(CriarAgente(nome="Sexto", papel="x"), cenario.contexto())
