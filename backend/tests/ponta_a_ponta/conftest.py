"""Servidor HTTP e worker reais, com Postgres e Redis do Docker."""

from uuid import uuid4

import httpx
import pytest
from arq.connections import ArqRedis
from arq.jobs import Job
from redis.asyncio import Redis

from tests.integracao.conftest import event_loop_policy, pytest_collection_modifyitems
from tests.integracao.relogio_base import mundo, servicos_relogio
from tests.ponta_a_ponta.http import entrar

__all__ = [
    "event_loop_policy",
    "mundo",
    "pytest_collection_modifyitems",
    "servicos_relogio",
]


@pytest.fixture
async def fila_arq(mundo):
    """Controle da infraestrutura ARQ, para aguardar jobs sem chamar sua função."""
    async with Redis.from_url(mundo.url_redis) as redis:
        yield ArqRedis(redis.connection_pool)


@pytest.fixture
def aguardar_job(fila_arq):
    async def aguardar(id_job):
        return await Job(id_job, redis=fila_arq).result(timeout=30, poll_delay=0.1)

    return aguardar


@pytest.fixture
async def cliente_e2e(mundo):
    async with httpx.AsyncClient(base_url=mundo.url, timeout=15) as cliente:
        cliente.headers.update(await entrar(cliente, mundo, f"{uuid4().hex}@exemplo.com"))
        yield cliente
