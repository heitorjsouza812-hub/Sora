"""Base dos testes de integração do Relógio: containers, API em uvicorn e worker ARQ reais."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from arq.connections import RedisSettings
from arq.worker import create_worker
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.banco import fabrica_sessoes
from app.core.config import obter_configuracao
from app.ferramentas import ambiente
from app.main import criar_aplicacao
from tests.integracao.test_fase_b_pronto import _fechar_worker, _porta_livre
from workers.configuracao import WorkerSettings

RAIZ = Path(__file__).resolve().parents[2]


class Mundo:
    def __init__(self, url: str, fabrica: async_sessionmaker, url_redis: str) -> None:
        self.url, self.fabrica, self.url_redis = url, fabrica, url_redis
        self._worker: Any = None
        self._tarefa: asyncio.Task | None = None

    async def iniciar_worker(self) -> None:
        self._worker = create_worker(
            WorkerSettings,
            redis_settings=RedisSettings.from_dsn(self.url_redis),
            handle_signals=False,
            poll_delay=0.1,
        )
        self._tarefa = asyncio.create_task(self._worker.async_run())

    async def parar_worker(self) -> None:
        if self._worker is not None:
            await _fechar_worker(self._worker)
            assert self._tarefa is not None
            self._tarefa.cancel()
            self._worker = self._tarefa = None


@pytest.fixture(scope="module")
def servicos_relogio():
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
async def mundo(
    servicos_relogio: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Mundo]:
    url_pg, url_redis = servicos_relogio
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
    redis = Redis.from_url(url_redis)
    await redis.flushdb()
    await redis.aclose()
    async with fabrica() as sessao:
        await sessao.execute(text("delete from convites where codigo = 'FASE-B'"))
        await sessao.execute(
            text("insert into convites (codigo, usos_restantes) values ('FASE-B', 50)")
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
    m = Mundo(f"http://127.0.0.1:{porta}", fabrica, url_redis)
    try:
        yield m
    finally:
        await m.parar_worker()
        servidor.should_exit = True
        await tarefa_api
        await motor.dispose()
        obter_configuracao.cache_clear()
        fabrica_sessoes.cache_clear()
        ambiente.redis_dos_eventos.cache_clear()


async def esperar(condicao: Callable[[], Any], limite_s: float = 60) -> Any:
    async def laco() -> Any:
        while True:
            valor = await condicao()
            if valor:
                return valor
            await asyncio.sleep(0.5)

    return await asyncio.wait_for(laco(), limite_s)
