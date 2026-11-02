"""Rotas do Trilho (conversas, cadeias, eventos) com Postgres e Redis reais e modelo falso."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import conversas as api_conversas
from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis
from app.main import criar_aplicacao
from app.modelos.tabelas import (
    Cadeia,
    Usuario,
)

pytestmark = pytest.mark.integracao

RAIZ = Path(__file__).resolve().parents[2]
SENHA = "senha-falsa-bem-longa"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


@dataclass
class FilaFalsa:
    """Registra o que iria para o ARQ; o conteúdo do job é o contrato com o Compasso."""

    jobs: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)

    async def enqueue_job(self, nome: str, *args: Any, **kwargs: Any) -> None:
        self.jobs.append((nome, args, kwargs))


@dataclass
class Ambiente:
    cliente: AsyncClient
    fabrica: async_sessionmaker[AsyncSession]
    fila: FilaFalsa
    redis: Any


@pytest.fixture(scope="module")
def servicos():
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    with (
        PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg") as pg,
        RedisContainer("redis:7") as rd,
    ):
        yield (
            pg.get_connection_url(),
            f"redis://{rd.get_container_host_ip()}:{rd.get_exposed_port(6379)}/0",
        )


@pytest.fixture
async def api(
    servicos: tuple[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[Ambiente]:
    from redis.asyncio import Redis

    url_pg, url_redis = servicos
    monkeypatch.setenv("DATABASE_URL", url_pg)
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    monkeypatch.setenv("PASTA_ARQUIVOS", str(tmp_path / "arquivos"))
    obter_configuracao.cache_clear()
    config = Config(str(RAIZ / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ / "migrations"))
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(command.upgrade, config, "head")
    motor = create_async_engine(url_pg)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    redis = Redis.from_url(url_redis, decode_responses=True)
    await redis.flushdb()
    async with fabrica() as sessao:
        await sessao.execute(
            text("insert into convites (codigo, usos_restantes) values ('CONVITE', 20)")
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

    fila = FilaFalsa()
    app = criar_aplicacao()
    app.dependency_overrides[obter_sessao] = sessao_de_teste
    app.dependency_overrides[obter_redis] = lambda: redis
    app.dependency_overrides[api_conversas.obter_fila] = lambda: fila
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://teste") as c:
            yield Ambiente(c, fabrica, fila, redis)
    finally:
        app.dependency_overrides.clear()
        obter_configuracao.cache_clear()
        await redis.aclose()
        await motor.dispose()


async def _entrar(api: Ambiente, email: str) -> tuple[dict[str, str], UUID]:
    cadastro = await api.cliente.post(
        "/v1/auth/cadastrar",
        json={"nome": "Ana", "email": email, "senha": SENHA, "convite": "CONVITE"},
    )
    assert cadastro.status_code == 201
    login = await api.cliente.post("/v1/auth/entrar", json={"email": email, "senha": SENHA})
    auth = {"Authorization": f"Bearer {login.json()['token_acesso']}"}
    async with api.fabrica() as sessao:
        usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
    assert usuario_id is not None
    return auth, usuario_id


@dataclass
class Cena:
    conversa_id: UUID
    cadeia_id: UUID
    etapa_id: UUID
    agente_id: UUID


async def test_pedido_cria_conversa_cadeia_job_e_eventos(api: Ambiente) -> None:
    auth, uid = await _entrar(api, "ana@exemplo.com")
    outro, _ = await _entrar(api, "bia@exemplo.com")
    resposta = await api.cliente.post(
        "/v1/conversas", json={"texto": "crie uma campanha para minha cafeteria"}, headers=auth
    )
    assert resposta.status_code == 201, resposta.text
    conversa_id = resposta.json()["id"]

    async with api.fabrica() as sessao:
        cadeia = await sessao.scalar(select(Cadeia).where(Cadeia.usuario_id == uid))
    assert cadeia is not None and str(cadeia.conversa_id) == conversa_id
    assert [(n, a) for n, a, _ in api.fila.jobs] == [("planejar_cadeia", (str(cadeia.id),))]

    url = f"/v1/conversas/{conversa_id}/mensagens"
    mensagens = (await api.cliente.get(url, headers=auth)).json()
    assert {m["autor"] for m in mensagens} >= {"usuario", "sora"}
    entradas = await api.redis.xrange(f"eventos:{conversa_id}")
    assert len(entradas) >= 3

    assert (await api.cliente.get(f"/v1/cadeias/{cadeia.id}", headers=auth)).status_code == 200
    assert (await api.cliente.get(f"/v1/cadeias/{cadeia.id}", headers=outro)).status_code == 404
    assert (await api.cliente.get(url, headers=outro)).status_code == 404

    for _ in range(2):
        cancelada = await api.cliente.post(f"/v1/cadeias/{cadeia.id}/cancelar", headers=auth)
        assert cancelada.status_code == 202

    renomeada = await api.cliente.patch(
        f"/v1/conversas/{conversa_id}", json={"titulo": "Cafeteria"}, headers=auth
    )
    assert renomeada.json()["titulo"] == "Cafeteria"
    apagar = f"/v1/conversas/{conversa_id}"
    assert (await api.cliente.delete(apagar, headers=outro)).status_code == 404
    assert (await api.cliente.delete(apagar, headers=auth)).status_code == 204
