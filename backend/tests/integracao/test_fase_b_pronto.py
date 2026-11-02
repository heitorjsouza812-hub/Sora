"""Prova de pronto da Fase B com Postgres/Redis reais e modelo falso."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from arq.connections import ArqRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis
from app.eventos.streams import canal_conversa
from app.main import criar_aplicacao
from app.modelos.enumeracoes import StatusCadeia, StatusEtapa, TipoProvedor
from app.modelos.tabelas import Cadeia, Etapa, ModeloDisponivel, Provedor, Usuario
from workers.cadeia import (
    entregar_resultado,
    executar_etapa,
    planejar_cadeia,
    verificar_cadeia,
)
from workers.fila import configurar_fila

pytestmark = pytest.mark.integracao

RAIZ = Path(__file__).resolve().parents[2]
SENHA = "uma-senha-bem-longa"


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


@pytest.fixture
async def ambiente_fase_b(
    servicos_fase_b: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker, object]]:
    from redis.asyncio import Redis

    url_pg, url_redis = servicos_fase_b
    monkeypatch.setenv("AMBIENTE", "teste")
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    monkeypatch.setenv("DATABASE_URL", url_pg)
    monkeypatch.setenv("REDIS_URL", url_redis)
    obter_configuracao.cache_clear()

    alembic = Config(str(RAIZ / "alembic.ini"))
    alembic.set_main_option("script_location", str(RAIZ / "migrations"))
    await asyncio.to_thread(command.upgrade, alembic, "head")
    motor = create_async_engine(url_pg)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    redis = Redis.from_url(url_redis, decode_responses=True)
    await redis.flushdb()
    async with fabrica() as sessao:
        await sessao.execute(
            text("insert into convites (codigo, usos_restantes) values ('FASE-B', 1)")
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


async def test_post_eventos_entrega_e_cadeia_concluida_com_modelo_falso(
    ambiente_fase_b: tuple[AsyncClient, async_sessionmaker, object],
) -> None:
    cliente, fabrica, redis = ambiente_fase_b
    cadastro = await cliente.post(
        "/v1/auth/cadastrar",
        json={
            "nome": "Ana",
            "email": "ana-fase-b@exemplo.com",
            "senha": SENHA,
            "convite": "FASE-B",
        },
    )
    assert cadastro.status_code == 201
    login = await cliente.post(
        "/v1/auth/entrar",
        json={"email": "ana-fase-b@exemplo.com", "senha": SENHA},
    )
    auth = {"Authorization": f"Bearer {login.json()['token_acesso']}"}

    async with fabrica() as sessao:
        usuario = await sessao.scalar(
            select(Usuario).where(Usuario.email == "ana-fase-b@exemplo.com")
        )
        assert usuario is not None
        provedor = Provedor(
            usuario_id=usuario.id,
            tipo=TipoProvedor.GROQ,
            validado_em=datetime.now(UTC),
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

    resposta = await cliente.post(
        "/v1/conversas",
        headers=auth,
        json={"texto": "crie uma campanha para minha cafeteria", "anexos": []},
    )
    assert resposta.status_code == 201, resposta.text
    conversa_id = resposta.json()["id"]

    async with fabrica() as sessao:
        cadeia = await sessao.scalar(select(Cadeia).where(Cadeia.conversa_id == conversa_id))
        assert cadeia is not None
        cadeia_id = cadeia.id

    contexto = {"sessoes": fabrica, "redis_eventos": redis}
    await planejar_cadeia(contexto, str(cadeia_id))
    async with fabrica() as sessao:
        etapas = list(
            (
                await sessao.scalars(
                    select(Etapa).where(Etapa.cadeia_id == cadeia_id).order_by(Etapa.ordem)
                )
            ).all()
        )
    pesquisador, redator, _verificador = etapas
    await executar_etapa(contexto, str(pesquisador.id))
    await executar_etapa(contexto, str(redator.id))
    await verificar_cadeia(contexto, str(cadeia_id))
    await entregar_resultado(contexto, str(cadeia_id))

    async with fabrica() as sessao:
        cadeia = await sessao.get(Cadeia, cadeia_id)
        assert cadeia is not None and cadeia.status == StatusCadeia.CONCLUIDA
        estados = list(
            (
                await sessao.scalars(
                    select(Etapa.status).where(Etapa.cadeia_id == cadeia_id).order_by(Etapa.ordem)
                )
            ).all()
        )
        assert estados == [StatusEtapa.CONCLUIDA] * 3

    entradas = await redis.xrange(canal_conversa(conversa_id))
    nomes = [campos["event"] for _, campos in entradas]
    dados = [json.loads(campos["data"]) for _, campos in entradas]
    assert nomes.count("agente.criado") == 3
    assert nomes.count("entrega") == 2
    assert "cadeia.criada" in nomes
    assert "etapa.atualizada" in nomes
    assert any(
        nome == "cadeia.atualizada" and dado["status"] == "concluida"
        for nome, dado in zip(nomes, dados, strict=True)
    )
