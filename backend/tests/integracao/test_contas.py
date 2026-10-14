"""Contas ponta a ponta com Postgres e Redis reais (Docker); especificação §8.2."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis
from app.main import criar_aplicacao
from app.modelos.tabelas import Agente, Sessao, Usuario

pytestmark = pytest.mark.integracao

RAIZ = Path(__file__).resolve().parents[2]
SENHA = "uma-senha-bem-longa"


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
async def cliente(servicos, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    from redis.asyncio import Redis

    url_pg, url_redis = servicos
    monkeypatch.setenv("DATABASE_URL", url_pg)
    config = Config(str(RAIZ / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ / "migrations"))
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(command.upgrade, config, "head")

    motor = create_async_engine(url_pg)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    redis = Redis.from_url(url_redis, decode_responses=True)
    await redis.flushdb()
    async with fabrica() as s:
        await s.execute(text("insert into convites (codigo, usos_restantes) values ('CONVITE', 3)"))
        await s.commit()

    async def sessao_de_teste():
        async with fabrica() as sessao:
            try:
                yield sessao
                await sessao.commit()
            except BaseException:
                await sessao.rollback()
                raise

    app = criar_aplicacao()
    app.dependency_overrides[obter_sessao] = sessao_de_teste
    app.dependency_overrides[obter_redis] = lambda: redis
    app.state.fabrica = fabrica
    transporte = ASGITransport(app=app)
    async with AsyncClient(transport=transporte, base_url="http://teste") as c:
        c.app_state = app.state  # type: ignore[attr-defined]
        yield c
    await redis.aclose()
    await motor.dispose()


async def _cadastrar(c: AsyncClient, email: str = "ana@exemplo.com", convite: str = "CONVITE"):
    return await c.post(
        "/v1/auth/cadastrar",
        json={"nome": "Ana", "email": email, "senha": SENHA, "convite": convite},
    )


async def test_cadastro_exige_convite_valido_e_consome_um_uso(cliente: AsyncClient) -> None:
    assert (await _cadastrar(cliente, convite="NAO-EXISTE")).status_code == 403
    assert (await _cadastrar(cliente)).status_code == 201
    assert (await _cadastrar(cliente)).status_code == 409  # e-mail repetido
    async with cliente.app_state.fabrica() as s:  # type: ignore[attr-defined]
        usos = await s.scalar(text("select usos_restantes from convites where codigo='CONVITE'"))
        sora = await s.scalar(select(Agente).where(Agente.nome == "Sora"))
    assert usos == 2
    assert sora is not None


async def test_login_web_e_desktop(cliente: AsyncClient) -> None:
    await _cadastrar(cliente)
    errado = await cliente.post(
        "/v1/auth/entrar", json={"email": "ana@exemplo.com", "senha": "x" * 12}
    )
    assert errado.status_code == 401
    web = await cliente.post("/v1/auth/entrar", json={"email": "ANA@exemplo.com", "senha": SENHA})
    assert web.status_code == 200
    assert "sora_renovacao" in web.cookies
    assert web.json()["token_renovacao"] is None
    desktop = await cliente.post(
        "/v1/auth/entrar",
        json={"email": "ana@exemplo.com", "senha": SENHA},
        headers={"X-Sora-Cliente": "desktop"},
    )
    assert desktop.json()["token_renovacao"]

    eu = await cliente.get(
        "/v1/eu", headers={"Authorization": f"Bearer {web.json()['token_acesso']}"}
    )
    assert eu.json() == {
        "nome": "Ana",
        "email": "ana@exemplo.com",
        "prioridade": "custo",
        "tem_provedor": False,
    }


async def test_renovacao_rotaciona_e_reuso_encerra_a_sessao(cliente: AsyncClient) -> None:
    await _cadastrar(cliente)
    login = await cliente.post(
        "/v1/auth/entrar",
        json={"email": "ana@exemplo.com", "senha": SENHA},
        headers={"X-Sora-Cliente": "desktop"},
    )
    t1 = login.json()["token_renovacao"]
    r2 = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t1})
    assert r2.status_code == 200
    t2 = r2.json()["token_renovacao"]
    assert t2 and t2 != t1

    reuso = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t1})
    assert reuso.status_code == 401
    # a sessão inteira caiu: nem o token novo funciona mais
    depois = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t2})
    assert depois.status_code == 401
    async with cliente.app_state.fabrica() as s:  # type: ignore[attr-defined]
        encerradas = await s.scalar(select(Sessao.encerrada_em).where(Sessao.token_hash != ""))
    assert encerradas is not None


async def test_sair_encerra_a_sessao(cliente: AsyncClient) -> None:
    await _cadastrar(cliente)
    login = await cliente.post(
        "/v1/auth/entrar",
        json={"email": "ana@exemplo.com", "senha": SENHA},
        headers={"X-Sora-Cliente": "desktop"},
    )
    token = login.json()["token_renovacao"]
    assert (await cliente.post("/v1/auth/sair", json={"token_renovacao": token})).status_code == 204
    assert (
        await cliente.post("/v1/auth/renovar", json={"token_renovacao": token})
    ).status_code == 401


async def test_limite_de_login_responde_429_com_retry_after(cliente: AsyncClient) -> None:
    await _cadastrar(cliente)
    for _ in range(5):
        r = await cliente.post(
            "/v1/auth/entrar", json={"email": "ana@exemplo.com", "senha": "errada-errada"}
        )
        assert r.status_code == 401
    bloqueado = await cliente.post(
        "/v1/auth/entrar", json={"email": "ana@exemplo.com", "senha": SENHA}
    )
    assert bloqueado.status_code == 429
    assert int(bloqueado.headers["retry-after"]) > 0


async def test_apagar_conta_confirma_senha_e_remove_tudo(cliente: AsyncClient) -> None:
    await _cadastrar(cliente)
    login = await cliente.post("/v1/auth/entrar", json={"email": "ana@exemplo.com", "senha": SENHA})
    auth = {"Authorization": f"Bearer {login.json()['token_acesso']}"}
    errada = await cliente.request(
        "DELETE", "/v1/conta", json={"senha": "senha-errada!"}, headers=auth
    )
    assert errada.status_code == 403
    ok = await cliente.request("DELETE", "/v1/conta", json={"senha": SENHA}, headers=auth)
    assert ok.status_code == 204
    async with cliente.app_state.fabrica() as s:  # type: ignore[attr-defined]
        assert await s.scalar(select(Usuario.id)) is None
        assert await s.scalar(select(Agente.id)) is None
        assert await s.scalar(select(Sessao.id)) is None
