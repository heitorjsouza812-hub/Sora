"""Contas ponta a ponta com Postgres e Redis reais (Docker); especificação §8.2."""

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import contas, seguranca
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


async def test_renovacao_tolera_resposta_perdida_e_reuso_tardio_encerra(
    cliente: AsyncClient,
) -> None:
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

    recuperada = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t1})
    assert recuperada.status_code == 200
    t3 = recuperada.json()["token_renovacao"]
    assert t3 == t2
    assert recuperada.json() == r2.json()

    # Simula a última rotação fora da janela de reemissão (5 min) sem esperar no teste.
    async with cliente.app_state.fabrica() as s:  # type: ignore[attr-defined]
        sessao = await s.scalar(select(Sessao).where(Sessao.token_hash == seguranca.hash_token(t3)))
        assert sessao is not None
        sessao.anterior_rotacionado_em -= contas.JANELA_REEMISSAO + timedelta(seconds=1)
        await s.commit()

    reuso = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t1})
    assert reuso.status_code == 401
    # A sessão inteira caiu e continua encerrada: nem o token atual funciona mais.
    depois = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t3})
    assert depois.status_code == 401
    async with cliente.app_state.fabrica() as s:  # type: ignore[attr-defined]
        encerradas = await s.scalar(select(Sessao.encerrada_em).where(Sessao.token_hash != ""))
    assert encerradas is not None


async def test_f5_seguidos_reemitem_e_o_token_abandonado_derruba_a_sessao(
    cliente: AsyncClient,
) -> None:
    """Decisão 6: três F5 com a resposta da renovação perdida não derrubam mais o login. Entre
    30 s e 5 min o token anterior ganha um par NOVO; o atual (nunca usado) fica abandonado e, se
    aparecer depois, havia duas cópias da sessão: ela cai inteira."""
    await _cadastrar(cliente)
    login = await cliente.post(
        "/v1/auth/entrar",
        json={"email": "ana@exemplo.com", "senha": SENHA},
        headers={"X-Sora-Cliente": "desktop"},
    )
    t1 = login.json()["token_renovacao"]
    t2 = (await cliente.post("/v1/auth/renovar", json={"token_renovacao": t1})).json()[
        "token_renovacao"
    ]  # resposta "perdida": o app continua só com t1

    async with cliente.app_state.fabrica() as s:  # type: ignore[attr-defined]
        sessao = await s.scalar(select(Sessao).where(Sessao.token_hash == seguranca.hash_token(t2)))
        assert sessao is not None
        sessao.anterior_rotacionado_em -= contas.JANELA_TOLERANCIA_RENOVACAO + timedelta(seconds=1)
        await s.commit()

    reemitida = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t1})
    assert reemitida.status_code == 200
    t3 = reemitida.json()["token_renovacao"]
    assert t3 not in (t1, t2)
    # o par novo funciona normalmente
    t4_resposta = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t3})
    assert t4_resposta.status_code == 200
    t4 = t4_resposta.json()["token_renovacao"]

    # t2 foi abandonado na reemissão: aparecer agora é reuso e derruba a sessão inteira
    assert (await cliente.post("/v1/auth/renovar", json={"token_renovacao": t2})).status_code == 401
    assert (await cliente.post("/v1/auth/renovar", json={"token_renovacao": t4})).status_code == 401


async def test_tres_renovacoes_concorrentes_usam_uma_unica_sessao(
    cliente: AsyncClient,
) -> None:
    await _cadastrar(cliente)
    login = await cliente.post(
        "/v1/auth/entrar",
        json={"email": "ana@exemplo.com", "senha": SENHA},
        headers={"X-Sora-Cliente": "desktop"},
    )
    inicial = login.json()["token_renovacao"]

    respostas = await asyncio.gather(
        cliente.post("/v1/auth/renovar", json={"token_renovacao": inicial}),
        cliente.post("/v1/auth/renovar", json={"token_renovacao": inicial}),
        cliente.post("/v1/auth/renovar", json={"token_renovacao": inicial}),
    )

    assert [resposta.status_code for resposta in respostas] == [200, 200, 200]
    devolvidos = {resposta.json()["token_renovacao"] for resposta in respostas}
    assert None not in devolvidos
    assert len(devolvidos) == 1
    async with cliente.app_state.fabrica() as s:  # type: ignore[attr-defined]
        sessoes = list((await s.scalars(select(Sessao))).all())
    assert len(sessoes) == 1
    assert sessoes[0].encerrada_em is None
    assert sessoes[0].token_hash == seguranca.hash_token(next(iter(devolvidos)))
    assert sessoes[0].anterior_hash == seguranca.hash_token(inicial)
    assert len({r.json()["token_acesso"] for r in respostas}) == 1


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


async def test_token_duas_geracoes_atras_revoga_familia(cliente: AsyncClient) -> None:
    await _cadastrar(cliente)
    login = await cliente.post(
        "/v1/auth/entrar",
        json={"email": "ana@exemplo.com", "senha": SENHA},
        headers={"X-Sora-Cliente": "desktop"},
    )
    t0 = login.json()["token_renovacao"]
    r1 = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t0})
    t1 = r1.json()["token_renovacao"]
    r2 = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t1})
    assert r2.status_code == 200
    assert (await cliente.post("/v1/auth/renovar", json={"token_renovacao": t0})).status_code == 401
    assert (
        await cliente.post(
            "/v1/auth/renovar", json={"token_renovacao": r2.json()["token_renovacao"]}
        )
    ).status_code == 401


async def test_par_cifrado_some_quando_a_janela_fecha_e_historico_tem_teto(
    cliente: AsyncClient,
) -> None:
    """Cerca M4: o token vivo não fica guardado no banco depois dos 30 s; o histórico é limitado."""
    await _cadastrar(cliente)
    login = await cliente.post(
        "/v1/auth/entrar",
        json={"email": "ana@exemplo.com", "senha": SENHA},
        headers={"X-Sora-Cliente": "desktop"},
    )
    t1 = login.json()["token_renovacao"]
    r2 = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t1})
    t2 = r2.json()["token_renovacao"]
    fabrica = cliente.app_state.fabrica  # type: ignore[attr-defined]

    async def sessao_atual(token: str) -> Sessao:
        async with fabrica() as s:
            achada = await s.scalar(
                select(Sessao).where(Sessao.token_hash == seguranca.hash_token(token))
            )
            assert achada is not None
            return achada

    # Dentro da janela o par existe (recuperação de resposta perdida) e a rotina não o toca.
    assert (await sessao_atual(t2)).par_atual_cifrado is not None
    async with fabrica() as s:
        assert await contas.limpar_pares_vencidos(s) == 0
    assert (await sessao_atual(t2)).par_atual_cifrado is not None

    # Janela fechada: a rotina apaga o par cifrado.
    async with fabrica() as s:
        await s.execute(
            text("update sessoes set anterior_rotacionado_em = now() - interval '31 seconds'")
        )
        await s.commit()
    async with fabrica() as s:
        assert await contas.limpar_pares_vencidos(s) == 1
    assert (await sessao_atual(t2)).par_atual_cifrado is None
    # O token atual continua renovando normalmente (gera par novo, com janela nova).
    r3 = await cliente.post("/v1/auth/renovar", json={"token_renovacao": t2})
    assert r3.status_code == 200
    t3 = r3.json()["token_renovacao"]
    assert (await sessao_atual(t3)).par_atual_cifrado is not None

    # Histórico com teto: depois de muitas rotações guarda só as últimas.
    atual = t3
    for _ in range(contas.MAX_HISTORICO_HASHES + 5):
        async with fabrica() as s:
            await s.execute(
                text("update sessoes set anterior_rotacionado_em = now() - interval '31 seconds'")
            )
            await s.commit()
        r = await cliente.post("/v1/auth/renovar", json={"token_renovacao": atual})
        assert r.status_code == 200
        atual = r.json()["token_renovacao"]
    sessao = await sessao_atual(atual)
    assert len(sessao.historico_hashes) == contas.MAX_HISTORICO_HASHES
    assert seguranca.hash_token(t1) not in sessao.historico_hashes  # gerações velhas esquecidas
    assert sessao.historico_hashes[-1] == sessao.anterior_hash

    # Sair apaga o par também.
    async with fabrica() as s:
        await contas.sair(s, atual)
        await s.commit()
    assert (await sessao_atual(atual)).par_atual_cifrado is None


async def test_apagar_conta_com_dados_em_todas_as_tabelas(cliente: AsyncClient) -> None:
    """Uma linha em CADA tabela do modelo, ligada ao usuário (inclusive as FKs que fecham ciclo,
    como ``agentes.perfil_navegador_id``), e o DELETE /v1/conta apaga tudo.

    Antes, ``apagar_conta`` listava ~21 tabelas à mão: com uma rotina, um grupo, a fila, o
    navegador ou os canais da empresa, o ``DELETE FROM usuarios`` falhava por chave estrangeira
    e a conta não era apagada (LGPD)."""
    import enum
    import uuid
    from datetime import UTC, date, datetime

    from sqlalchemy import (
        ARRAY,
        JSON,
        Boolean,
        Date,
        DateTime,
        Enum,
        Float,
        Integer,
        LargeBinary,
        Numeric,
        String,
        Text,
        Uuid,
        insert,
        update,
    )
    from sqlalchemy.dialects.postgresql import INET, JSONB

    from app.core.contas import TABELAS_SEM_DONO, _quebra_ciclo, _tabelas_do_banco

    await _cadastrar(cliente)
    login = await cliente.post("/v1/auth/entrar", json={"email": "ana@exemplo.com", "senha": SENHA})
    auth = {"Authorization": f"Bearer {login.json()['token_acesso']}"}
    fabrica = cliente.app_state.fabrica  # type: ignore[attr-defined]

    def valor(coluna):
        tipo = coluna.type
        if isinstance(tipo, Enum):
            primeiro = tipo.enums[0]
            classe = getattr(tipo, "enum_class", None)
            if classe is not None and issubclass(classe, enum.Enum):
                return next(m for m in classe if m.value == primeiro or m.name == primeiro)
            return primeiro
        if isinstance(tipo, Uuid):
            return uuid.uuid4()
        if isinstance(tipo, (Text, String)):
            return "x"
        if isinstance(tipo, Boolean):
            return False
        if isinstance(tipo, (Integer, Numeric, Float)):
            return 1
        if isinstance(tipo, DateTime):
            return datetime.now(UTC)
        if isinstance(tipo, Date):
            return date.today()
        if isinstance(tipo, (JSONB, JSON)):
            return {}
        if isinstance(tipo, ARRAY):
            return []
        if isinstance(tipo, INET):
            return "127.0.0.1"
        if isinstance(tipo, LargeBinary):
            return b"x"
        if getattr(tipo, "dim", None):  # pgvector
            return [0.0] * tipo.dim
        raise AssertionError(f"tipo sem valor de teste: {coluna.table.name}.{coluna.name} {tipo}")

    async with fabrica() as s:
        usuario_id = await s.scalar(select(Usuario.id))
        criados: dict[str, dict[str, object]] = {"usuarios": {"id": usuario_id}}
        for tabela in _tabelas_do_banco():
            if tabela.name in TABELAS_SEM_DONO:
                continue
            linha: dict[str, object] = {}
            for coluna in tabela.columns:
                fks = [fk for fk in coluna.foreign_keys if not _quebra_ciclo(fk)]
                alvo = fks[0].column if fks else None
                if alvo is not None and alvo.table.name in criados:
                    linha[coluna.name] = criados[alvo.table.name][alvo.name]
                elif alvo is not None and alvo.table is tabela:
                    continue  # autorreferência: fica nula
                elif (
                    not coluna.nullable and coluna.default is None and coluna.server_default is None
                ):
                    linha[coluna.name] = valor(coluna)
                elif coluna.primary_key and coluna.default is None:
                    linha[coluna.name] = valor(coluna)
            colunas = list(tabela.primary_key.columns) + [
                c for c in tabela.columns if not c.primary_key
            ]
            devolvido = (
                (await s.execute(insert(tabela).values(linha).returning(*colunas))).mappings().one()
            )
            criados[tabela.name] = dict(devolvido)
        # FKs que fecham ciclo (agentes.cadeia_id, agentes.perfil_navegador_id, ...)
        for tabela in _tabelas_do_banco():
            for fk in tabela.foreign_keys:
                if _quebra_ciclo(fk) and tabela.name in criados and fk.column.table.name in criados:
                    pk = list(tabela.primary_key.columns)
                    await s.execute(
                        update(tabela)
                        .where(*[c == criados[tabela.name][c.name] for c in pk])
                        .values({fk.parent.name: criados[fk.column.table.name][fk.column.name]})
                    )
        await s.commit()

    resposta = await cliente.request("DELETE", "/v1/conta", json={"senha": SENHA}, headers=auth)
    assert resposta.status_code == 204, resposta.text
    async with fabrica() as s:
        sobrou = {
            t.name: n
            for t in _tabelas_do_banco()
            if t.name not in TABELAS_SEM_DONO
            and (n := await s.scalar(text(f"select count(*) from {t.name}")))
        }
    assert sobrou == {}
