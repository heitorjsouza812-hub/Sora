"""Prova de pronto da Fase B: API real, worker ARQ real e SSE real.

Postgres e Redis em Docker; ``SORA_MODELO_FALSO=1``. Nada de chamar job direto: a API enfileira
no Redis e um ``arq.Worker`` com as ``WorkerSettings`` de verdade consome a fila (incluindo o
checkpointer do LangGraph no Postgres). O teste só fala HTTP e lê o SSE.
"""

from __future__ import annotations

import asyncio
import json
import signal
import socket
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from arq.connections import ArqRedis, RedisSettings, create_pool
from arq.worker import create_worker
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.banco import fabrica_sessoes, obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis
from app.ferramentas import ambiente
from app.main import criar_aplicacao
from app.modelos.enumeracoes import (
    AutorMensagem,
    DecisaoAprovacao,
    StatusAprovacao,
    StatusCadeia,
    StatusEtapa,
    TipoAgente,
    TipoConversa,
    TipoProvedor,
)
from app.modelos.tabelas import (
    Agente,
    Aprovacao,
    Cadeia,
    Conversa,
    Entrega,
    Etapa,
    Mensagem,
    ModeloDisponivel,
    Provedor,
    Usuario,
)
from workers.configuracao import WorkerSettings
from workers.fila import configurar_fila

pytestmark = pytest.mark.integracao

RAIZ = Path(__file__).resolve().parents[2]


async def _fechar_worker(worker: Any) -> None:
    """Contorna o ARQ propagando CancelledError dos jobs durante o encerramento."""
    try:
        await worker.close()
    except asyncio.CancelledError:
        worker.tasks.clear()
        await worker.close()


SENHA = "uma-senha-bem-longa"
LIMITE_S = 90


@pytest.fixture(scope="module")
def servicos_fase_b():
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


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def ambiente_fase_b(
    servicos_fase_b: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker, Redis]]:
    """Fixture pequeno mantido para os testes isolados do agente do Compasso."""
    url_pg, url_redis = servicos_fase_b
    monkeypatch.setenv("AMBIENTE", "teste")
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    monkeypatch.setenv("BUSCA_PROVEDOR", "falso")
    monkeypatch.setenv("DATABASE_URL", url_pg)
    monkeypatch.setenv("REDIS_URL", url_redis)
    obter_configuracao.cache_clear()
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()

    alembic = Config(str(RAIZ / "alembic.ini"))
    alembic.set_main_option("script_location", str(RAIZ / "migrations"))
    await asyncio.to_thread(command.upgrade, alembic, "head")
    motor = create_async_engine(url_pg)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    redis = Redis.from_url(url_redis, decode_responses=True)
    await redis.flushdb()
    async with fabrica() as sessao:
        await sessao.execute(text("delete from convites where codigo = 'FASE-B'"))
        await sessao.execute(
            text("insert into convites (codigo, usos_restantes) values ('FASE-B', 10)")
        )
        await sessao.commit()

    async def sessao_de_teste():
        async with fabrica() as sessao:
            try:
                yield sessao
                await sessao.commit()
            except BaseException:
                await sessao.rollback()
                raise

    aplicacao = criar_aplicacao()
    aplicacao.dependency_overrides[obter_sessao] = sessao_de_teste
    aplicacao.dependency_overrides[obter_redis] = lambda: redis
    configurar_fila(ArqRedis(redis.connection_pool))
    async with AsyncClient(
        transport=ASGITransport(app=aplicacao), base_url="http://teste"
    ) as cliente:
        yield cliente, fabrica, redis
    configurar_fila(None)
    await redis.aclose()
    await motor.dispose()
    obter_configuracao.cache_clear()
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()


@pytest.fixture
async def ambiente_fase_b_arq(
    servicos_fase_b: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[str, async_sessionmaker]]:
    """API em uvicorn + worker ARQ rodando de verdade. Devolve (url_da_api, fabrica_de_sessoes)."""
    url_pg, url_redis = servicos_fase_b
    # arq.Worker.close() usa SIGUSR1, que não existe no Windows (só para registrar o desligamento)
    monkeypatch.setattr(signal, "SIGUSR1", signal.SIGTERM, raising=False)
    monkeypatch.setenv("AMBIENTE", "teste")
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    monkeypatch.setenv("BUSCA_PROVEDOR", "falso")
    monkeypatch.setenv("DATABASE_URL", url_pg)
    monkeypatch.setenv("REDIS_URL", url_redis)
    obter_configuracao.cache_clear()
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()

    alembic = Config(str(RAIZ / "alembic.ini"))
    alembic.set_main_option("script_location", str(RAIZ / "migrations"))
    await asyncio.to_thread(command.upgrade, alembic, "head")
    motor = create_async_engine(url_pg)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as sessao:
        await sessao.execute(text("delete from convites where codigo = 'FASE-B'"))
        await sessao.execute(
            text("insert into convites (codigo, usos_restantes) values ('FASE-B', 10)")
        )
        await sessao.commit()

    porta = _porta_livre()
    servidor = uvicorn.Server(
        uvicorn.Config(
            criar_aplicacao(), host="127.0.0.1", port=porta, log_level="warning", lifespan="on"
        )
    )
    tarefa_api = asyncio.create_task(servidor.serve())
    while not servidor.started:  # noqa: ASYNC110
        await asyncio.sleep(0.05)

    worker = create_worker(
        WorkerSettings,
        redis_settings=RedisSettings.from_dsn(url_redis),
        handle_signals=False,
        poll_delay=0.1,
    )
    tarefa_worker = asyncio.create_task(worker.async_run())
    try:
        yield f"http://127.0.0.1:{porta}", fabrica
    finally:
        await _fechar_worker(worker)
        tarefa_worker.cancel()
        servidor.should_exit = True
        await tarefa_api
        await motor.dispose()
        obter_configuracao.cache_clear()
        fabrica_sessoes.cache_clear()
        ambiente.redis_dos_eventos.cache_clear()


async def entrar(cliente: httpx.AsyncClient, fabrica: async_sessionmaker, email: str) -> dict:
    cadastro = await cliente.post(
        "/v1/auth/cadastrar",
        json={"nome": "Ana", "email": email, "senha": SENHA, "convite": "FASE-B"},
    )
    assert cadastro.status_code == 201, cadastro.text
    login = await cliente.post("/v1/auth/entrar", json={"email": email, "senha": SENHA})
    async with fabrica() as sessao:
        usuario = await sessao.scalar(select(Usuario).where(Usuario.email == email))
        assert usuario is not None
        if not await sessao.scalar(select(Provedor.id).where(Provedor.usuario_id == usuario.id)):
            provedor = Provedor(
                usuario_id=usuario.id, tipo=TipoProvedor.GROQ, validado_em=datetime.now(UTC)
            )
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
    return {"Authorization": f"Bearer {login.json()['token_acesso']}"}


async def ler_sse(
    cliente: httpx.AsyncClient,
    conversa_id: str,
    auth: dict,
    *,
    ate: Any,
    limite_s: float = LIMITE_S,
) -> list[tuple[str, dict]]:
    """Lê o SSE da conversa desde o início até ``ate(nome, dados)`` ser verdadeiro."""
    eventos: list[tuple[str, dict]] = []

    async def ler() -> None:
        async with cliente.stream(
            "GET",
            f"/v1/conversas/{conversa_id}/eventos",
            headers={**auth, "Last-Event-ID": "0-0"},
            timeout=None,
        ) as resposta:
            assert resposta.status_code == 200
            nome = None
            async for linha in resposta.aiter_lines():
                if linha.startswith("event:"):
                    nome = linha.split(":", 1)[1].strip()
                elif linha.startswith("data:") and nome:
                    dados = json.loads(linha.split(":", 1)[1])
                    eventos.append((nome, dados))
                    if ate(nome, dados):
                        return

    await asyncio.wait_for(ler(), timeout=limite_s)
    return eventos


def _concluiu(versao: int | None = None):
    def teste(nome: str, dados: dict) -> bool:
        return nome == "cadeia.atualizada" and dados.get("status") == "concluida"

    return teste


async def test_cadeia_de_ponta_a_ponta_com_worker_arq_real(
    ambiente_fase_b_arq: tuple[str, async_sessionmaker],
) -> None:
    url, fabrica = ambiente_fase_b_arq
    async with httpx.AsyncClient(base_url=url, timeout=30) as cliente:
        auth = await entrar(cliente, fabrica, "ana-fase-b@exemplo.com")

        # ---- cadeia: POST -> plano -> agentes -> etapas -> entregas -> verificador -> resposta
        resposta = await cliente.post(
            "/v1/conversas",
            headers=auth,
            json={"texto": "crie uma campanha para minha cafeteria", "anexos": []},
        )
        assert resposta.status_code == 201, resposta.text
        conversa_id = resposta.json()["id"]
        eventos = await ler_sse(cliente, conversa_id, auth, ate=_concluiu())
        nomes = [n for n, _ in eventos]
        assert nomes.count("agente.criado") == 3
        assert nomes.count("entrega") == 2
        assert "roteamento" in nomes and "cadeia.criada" in nomes
        assert "etapa.atualizada" in nomes and "mensagem.fim" in nomes

        async with fabrica() as sessao:
            cadeia = await sessao.scalar(select(Cadeia).where(Cadeia.conversa_id == conversa_id))
            assert cadeia is not None and cadeia.status == StatusCadeia.CONCLUIDA
            estados = list(
                (
                    await sessao.scalars(
                        select(Etapa.status)
                        .where(Etapa.cadeia_id == cadeia.id)
                        .order_by(Etapa.ordem)
                    )
                ).all()
            )
            assert estados == [StatusEtapa.CONCLUIDA] * 3
            entregas = (
                await sessao.scalars(select(Entrega).where(Entrega.cadeia_id == cadeia.id))
            ).all()
            assert len(entregas) == 2  # a ferramenta gravou; o worker não duplicou

        # ---- ajuste: versão 2 só com o especialista certo e o Verificador
        ajuste = await cliente.post(
            f"/v1/conversas/{conversa_id}/ajuste",
            headers=auth,
            json={"texto": "deixe o texto mais descontraído"},
        )
        assert ajuste.status_code == 202, ajuste.text
        for _ in range(LIMITE_S * 5):
            async with fabrica() as sessao:
                v2 = await sessao.scalar(
                    select(Cadeia).where(Cadeia.conversa_id == conversa_id, Cadeia.versao == 2)
                )
                if v2 is not None and v2.status == StatusCadeia.CONCLUIDA:
                    break
            await asyncio.sleep(0.2)
        else:
            pytest.fail("a versão 2 não concluiu")
        async with fabrica() as sessao:
            etapas_v2 = (await sessao.scalars(select(Etapa).where(Etapa.cadeia_id == v2.id))).all()
            assert sorted(e.especialista for e in etapas_v2) == ["redator", "verificador"]

        # ---- resposta direta: um simples "oi" também precisa funcionar
        direta = await cliente.post(
            "/v1/conversas", headers=auth, json={"texto": "oi", "anexos": []}
        )
        assert direta.status_code == 201, direta.text
        id_direta = direta.json()["id"]
        eventos = await ler_sse(cliente, id_direta, auth, ate=lambda n, d: n == "sugestoes")
        nomes = [n for n, _ in eventos]
        assert "roteamento" in nomes and "cadeia.criada" not in nomes
        assert nomes.count("mensagem.fim") >= 2  # primeira resposta + a da Sora
        async with fabrica() as sessao:
            falas = (
                await sessao.scalars(
                    select(Mensagem.conteudo).where(
                        Mensagem.conversa_id == id_direta, Mensagem.autor == "sora"
                    )
                )
            ).all()
            assert any("resposta de exemplo" in f for f in falas), falas


async def _esperar_aprovacao(
    fabrica: async_sessionmaker, etapa_id, limite_s: float = 20
) -> Aprovacao:
    for _ in range(int(limite_s * 5)):
        async with fabrica() as sessao:
            aprovacao = await sessao.scalar(select(Aprovacao).where(Aprovacao.etapa_id == etapa_id))
            etapa = await sessao.get(Etapa, etapa_id)
            if aprovacao is not None and etapa.status == StatusEtapa.AGUARDANDO_APROVACAO:
                return aprovacao
        await asyncio.sleep(0.2)
    async with fabrica() as sessao:
        etapa = await sessao.get(Etapa, etapa_id)
        aprovacoes = list(
            await sessao.scalars(select(Aprovacao).where(Aprovacao.etapa_id == etapa_id))
        )
    raise AssertionError(
        "a etapa não chegou a aguardando_aprovacao: "
        f"status={etapa.status}, erro={etapa.erro!r}, aprovacoes={len(aprovacoes)}"
    )


async def test_modelo_http_do_seletor_criar_agente_pausa_e_retoma(
    servicos_fase_b: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """O worker usa o modelo HTTP escolhido no banco e retoma ``criar_agente`` pela API."""
    url_pg, url_redis = servicos_fase_b
    chamadas: list[dict[str, Any]] = []
    api_modelo = FastAPI()

    @api_modelo.post("/v1/chat/completions")
    async def completar(requisicao: Request) -> dict[str, Any]:
        corpo = await requisicao.json()
        chamadas.append(corpo)
        retomou = len(chamadas) > 1
        if retomou:
            nome = "entregar"
            argumentos = {
                "tipo": "texto",
                "titulo": "Agente proposto",
                "resumo": "1 agente criado com aprovação",
                "conteudo": "A criação foi aprovada e concluída.",
            }
        else:
            nome = "criar_agente"
            argumentos = {"nome": "Íris", "papel": "Organizar pesquisas"}
        return {
            "id": f"local-{len(chamadas)}",
            "object": "chat.completion",
            "created": 1,
            "model": "modelo-local",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": f"call-{len(chamadas)}",
                                "type": "function",
                                "function": {
                                    "name": nome,
                                    "arguments": json.dumps(argumentos, ensure_ascii=False),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }

    porta_modelo = _porta_livre()
    servidor_modelo = uvicorn.Server(
        uvicorn.Config(
            api_modelo,
            host="127.0.0.1",
            port=porta_modelo,
            log_level="warning",
            lifespan="off",
        )
    )
    tarefa_modelo = asyncio.create_task(servidor_modelo.serve())
    while not servidor_modelo.started:  # noqa: ASYNC110
        await asyncio.sleep(0.05)

    monkeypatch.setattr(signal, "SIGUSR1", signal.SIGTERM, raising=False)
    monkeypatch.setenv("AMBIENTE", "teste")
    monkeypatch.setenv("SORA_MODELO_FALSO", "0")
    monkeypatch.setenv("PERMITIR_PROVEDOR_REDE_LOCAL", "1")
    monkeypatch.setenv("BUSCA_PROVEDOR", "falso")
    monkeypatch.setenv("DATABASE_URL", url_pg)
    monkeypatch.setenv("REDIS_URL", url_redis)
    obter_configuracao.cache_clear()
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()

    alembic = Config(str(RAIZ / "alembic.ini"))
    alembic.set_main_option("script_location", str(RAIZ / "migrations"))
    await asyncio.to_thread(command.upgrade, alembic, "head")
    redis = Redis.from_url(url_redis, decode_responses=True)
    await redis.flushdb()
    motor = create_async_engine(url_pg)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as sessao:
        await sessao.execute(text("delete from convites where codigo = 'FASE-B'"))
        await sessao.execute(
            text("insert into convites (codigo, usos_restantes) values ('FASE-B', 10)")
        )
        await sessao.commit()
    porta_api = _porta_livre()
    servidor_api = uvicorn.Server(
        uvicorn.Config(
            criar_aplicacao(),
            host="127.0.0.1",
            port=porta_api,
            log_level="warning",
            lifespan="on",
        )
    )
    tarefa_api = asyncio.create_task(servidor_api.serve())
    while not servidor_api.started:  # noqa: ASYNC110
        await asyncio.sleep(0.05)
    worker = create_worker(
        WorkerSettings,
        redis_settings=RedisSettings.from_dsn(url_redis),
        handle_signals=False,
        poll_delay=0.1,
    )
    tarefa_worker = asyncio.create_task(worker.async_run())

    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{porta_api}", timeout=30
        ) as cliente:
            auth = await entrar(cliente, fabrica, "modelo-local@exemplo.com")
            async with fabrica() as sessao:
                usuario = await sessao.scalar(
                    select(Usuario).where(Usuario.email == "modelo-local@exemplo.com")
                )
                assert usuario is not None
                await sessao.execute(
                    text(
                        "delete from modelos_disponiveis where provedor_id in "
                        "(select id from provedores where usuario_id = :usuario)"
                    ),
                    {"usuario": usuario.id},
                )
                await sessao.execute(
                    text("delete from provedores where usuario_id = :usuario"),
                    {"usuario": usuario.id},
                )
                provedor = Provedor(
                    usuario_id=usuario.id,
                    tipo=TipoProvedor.COMPATIVEL_OPENAI,
                    base_url=f"http://127.0.0.1:{porta_modelo}/v1",
                    validado_em=datetime.now(UTC),
                )
                sessao.add(provedor)
                await sessao.flush()
                sessao.add(
                    ModeloDisponivel(
                        provedor_id=provedor.id,
                        modelo="openai/modelo-local",
                        nivel="N2",
                        capacidades=["ferramentas", "json"],
                        contexto=32_000,
                        velocidade_tps=100,
                    )
                )
                sora = await sessao.scalar(
                    select(Agente).where(
                        Agente.usuario_id == usuario.id, Agente.tipo == TipoAgente.SORA
                    )
                )
                assert sora is not None
                conversa = Conversa(
                    usuario_id=usuario.id,
                    agente_id=sora.id,
                    tipo=TipoConversa.PROJETO,
                    titulo="Criar agente com aprovação",
                )
                sessao.add(conversa)
                await sessao.flush()
                pedido = Mensagem(
                    conversa_id=conversa.id,
                    autor=AutorMensagem.USUARIO,
                    conteudo="Crie um agente para organizar pesquisas.",
                    anexos=[],
                    visivel=True,
                )
                sessao.add(pedido)
                await sessao.flush()
                cadeia = Cadeia(
                    usuario_id=usuario.id,
                    conversa_id=conversa.id,
                    pedido_id=pedido.id,
                    status=StatusCadeia.EXECUTANDO,
                    plano={
                        "objetivo": "Criar um agente aprovado pelo usuário",
                        "requisitos": ["O agente foi criado"],
                        "etapas": [{"ordem": 1, "pronto_quando": "O agente existe na conta"}],
                    },
                    orcamento_tokens=20_000,
                )
                sessao.add(cadeia)
                await sessao.flush()
                etapa = Etapa(
                    cadeia_id=cadeia.id,
                    ordem=1,
                    depende_de=[],
                    especialista="pesquisador",
                    agente_id=sora.id,
                    titulo="Criar agente",
                    nivel="N2",
                    tarefa="Crie o agente solicitado e entregue o resultado.",
                    status=StatusEtapa.PENDENTE,
                )
                sessao.add(etapa)
                await sessao.commit()
                etapa_id = etapa.id

            fila = await create_pool(RedisSettings.from_dsn(url_redis))
            try:
                await fila.enqueue_job("executar_etapa", str(etapa_id), _job_id=f"teste:{etapa_id}")
            finally:
                await fila.aclose()

            aprovacao = await _esperar_aprovacao(fabrica, etapa_id)
            assert aprovacao.status == StatusAprovacao.PENDENTE
            decisao = await cliente.post(
                f"/v1/aprovacoes/{aprovacao.id}/decidir",
                headers=auth,
                json={"decisao": DecisaoAprovacao.PERMITIR_UMA_VEZ.value},
            )
            assert decisao.status_code == 204, decisao.text

            for _ in range(20 * 5):
                async with fabrica() as sessao:
                    final = await sessao.get(Etapa, etapa_id)
                    iris = await sessao.scalar(
                        select(Agente).where(
                            Agente.usuario_id == usuario.id,
                            Agente.nome == "Íris",
                        )
                    )
                    if final.status == StatusEtapa.CONCLUIDA and iris is not None:
                        break
                await asyncio.sleep(0.2)
            else:
                async with fabrica() as sessao:
                    final = await sessao.get(Etapa, etapa_id)
                    aprovacoes = list(
                        await sessao.scalars(
                            select(Aprovacao).where(Aprovacao.etapa_id == etapa_id)
                        )
                    )
                pytest.fail(
                    "a etapa não retomou e concluiu após a aprovação: "
                    f"status={final.status}, erro={final.erro!r}, "
                    f"aprovações={[a.status for a in aprovacoes]}, chamadas={len(chamadas)}"
                )

            assert len(chamadas) >= 2
            assert {c["model"] for c in chamadas} == {"modelo-local"}
            assert any(
                ferramenta["function"]["name"] == "criar_agente"
                for ferramenta in chamadas[0]["tools"]
            )
    finally:
        await _fechar_worker(worker)
        tarefa_worker.cancel()
        servidor_api.should_exit = True
        await tarefa_api
        servidor_modelo.should_exit = True
        await tarefa_modelo
        await redis.aclose()
        await motor.dispose()
        obter_configuracao.cache_clear()
        fabrica_sessoes.cache_clear()
        ambiente.redis_dos_eventos.cache_clear()
