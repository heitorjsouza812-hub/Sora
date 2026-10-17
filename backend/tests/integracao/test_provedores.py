"""Fluxo ponta a ponta das APIs de modelos com PostgreSQL e Redis reais."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.provedores import obter_listador
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis
from app.core.seguranca import decifrar_segredo
from app.llm.provedores import (
    ChaveInvalida,
    ConfigProvedor,
    DestinoBloqueado,
    ErroProvedor,
)
from app.main import criar_aplicacao
from app.modelos.tabelas import ModeloDisponivel, Provedor, Usuario
from app.seletor.catalogo import obter_catalogo

pytestmark = pytest.mark.integracao

RAIZ = Path(__file__).resolve().parents[2]
SENHA = "senha-falsa-bem-longa"
CHAVE_ORIGINAL = "sk-TESTE-NAO-VAZAR-1234567890"
CHAVE_NOVA = "sk-TESTE-NOVA-NAO-VAZAR-0987654321"
CHAVE_INVALIDA = "sk-TESTE-INVALIDA-NAO-VAZAR-1111"
CHAVE_COM_ERRO = "sk-TESTE-ERRO-NAO-VAZAR-2222"
CHAVE_BLOQUEADA = "sk-TESTE-BLOQUEADA-NAO-VAZAR-3333"
CHAVE_LISTA_VAZIA = "sk-TESTE-VAZIA-NAO-VAZAR-4444"
CHAVE_MUITOS_MODELOS = "sk-TESTE-500-NAO-VAZAR-5555"
CHAVE_CURTA = "curta"
SEGREDOS_MARCADORES = (
    CHAVE_ORIGINAL,
    CHAVE_NOVA,
    CHAVE_INVALIDA,
    CHAVE_COM_ERRO,
    CHAVE_BLOQUEADA,
    CHAVE_LISTA_VAZIA,
    CHAVE_MUITOS_MODELOS,
    CHAVE_CURTA,
)

MODELOS_INICIAIS = [
    "openai/modelo-fora-do-catalogo",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
]
MODELOS_SINCRONIZADOS = [
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-luna",
]


@dataclass
class ListadorFalso:
    """Listador determinístico: nenhuma chamada de teste sai para a internet."""

    respostas: dict[str | None, list[str] | Exception] = field(default_factory=dict)
    chamadas: list[ConfigProvedor] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.respostas.update(
            {
                CHAVE_ORIGINAL: MODELOS_INICIAIS,
                CHAVE_NOVA: MODELOS_SINCRONIZADOS,
                CHAVE_INVALIDA: ChaveInvalida("O provedor recusou a chave."),
                CHAVE_COM_ERRO: ErroProvedor("Não foi possível conectar ao provedor."),
                CHAVE_BLOQUEADA: DestinoBloqueado(
                    "A URL da API aponta para a rede local, o que não é permitido."
                ),
                CHAVE_LISTA_VAZIA: [],
            }
        )

    async def __call__(self, config: ConfigProvedor) -> list[str]:
        self.chamadas.append(config)
        chave = config.api_key.get_secret_value() if config.api_key is not None else None
        resultado = self.respostas.get(chave, ["openai/gpt-5.6-luna"])
        if isinstance(resultado, Exception):
            raise resultado
        return list(resultado)


@dataclass
class AmbienteAPI:
    cliente: AsyncClient
    fabrica: async_sessionmaker[AsyncSession]
    listador: ListadorFalso
    respostas: list[Response]


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
    servicos: tuple[str, str], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> AsyncIterator[AmbienteAPI]:
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

    listador = ListadorFalso()
    respostas: list[Response] = []

    async def guardar_resposta(resposta: Response) -> None:
        respostas.append(resposta)

    app = criar_aplicacao()
    app.dependency_overrides[obter_sessao] = sessao_de_teste
    app.dependency_overrides[obter_redis] = lambda: redis
    app.dependency_overrides[obter_listador] = lambda: listador
    transporte = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transporte,
            base_url="http://teste",
            event_hooks={"response": [guardar_resposta]},
        ) as cliente:
            yield AmbienteAPI(cliente, fabrica, listador, respostas)
    finally:
        app.dependency_overrides.clear()
        texto_respostas = "\n".join(resposta.text for resposta in respostas)
        for segredo in SEGREDOS_MARCADORES:
            assert segredo not in texto_respostas
            assert segredo not in caplog.text
        await redis.aclose()
        await motor.dispose()


async def _cadastrar_e_entrar(
    cliente: AsyncClient, email: str = "ana@exemplo.com"
) -> dict[str, str]:
    cadastro = await cliente.post(
        "/v1/auth/cadastrar",
        json={"nome": "Ana", "email": email, "senha": SENHA, "convite": "CONVITE"},
    )
    assert cadastro.status_code == 201
    login = await cliente.post("/v1/auth/entrar", json={"email": email, "senha": SENHA})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['token_acesso']}"}


async def _usuario_id(api: AmbienteAPI, email: str = "ana@exemplo.com"):
    async with api.fabrica() as sessao:
        usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
    assert usuario_id is not None
    return usuario_id


def _por_modelo(itens: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["modelo"]: item for item in itens}


async def test_fluxo_completo_conecta_configura_sincroniza_e_apaga(api: AmbienteAPI) -> None:
    auth = await _cadastrar_e_entrar(api.cliente)
    antes = await api.cliente.get("/v1/eu", headers=auth)
    assert antes.status_code == 200
    assert antes.json()["tem_provedor"] is False

    conexao = await api.cliente.post(
        "/v1/provedores",
        json={"tipo": "openai", "chave": f"  {CHAVE_ORIGINAL}  "},
        headers=auth,
    )
    assert conexao.status_code == 201
    corpo = conexao.json()
    provedor_saida = corpo["provedor"]
    provedor_id = provedor_saida["id"]
    assert provedor_saida["tipo"] == "openai"
    assert provedor_saida["base_url"] is None
    assert provedor_saida["chave_final"] == "7890"
    assert len(corpo["modelos"]) == len(MODELOS_INICIAIS)
    assert api.listador.chamadas[-1].api_key is not None
    assert api.listador.chamadas[-1].api_key.get_secret_value() == CHAVE_ORIGINAL
    assert CHAVE_ORIGINAL not in repr(api.listador.chamadas[-1])

    usuario_id = await _usuario_id(api)
    catalogo = obter_catalogo()
    async with api.fabrica() as sessao:
        provedor = await sessao.get(Provedor, provedor_id)
        modelos = list(
            await sessao.scalars(
                select(ModeloDisponivel).where(ModeloDisponivel.provedor_id == provedor_id)
            )
        )
    assert provedor is not None
    assert provedor.chave_cifrada is not None
    assert CHAVE_ORIGINAL.encode() not in provedor.chave_cifrada
    assert (
        decifrar_segredo(provedor.chave_cifrada, usuario_id=usuario_id, provedor=str(provedor.id))
        == CHAVE_ORIGINAL
    )
    assert provedor.validado_em is not None
    assert {modelo.modelo for modelo in modelos} == set(MODELOS_INICIAIS)
    for modelo in modelos:
        classificacao = catalogo.classificar(modelo.modelo)
        assert modelo.nivel == classificacao.nivel
        assert modelo.capacidades == classificacao.capacidades
        assert modelo.contexto == classificacao.contexto
        assert modelo.preco_entrada == classificacao.preco_entrada
        assert modelo.preco_saida == classificacao.preco_saida
        assert modelo.velocidade_tps == classificacao.velocidade_tps
        assert modelo.origem == classificacao.origem
        assert modelo.ativo is (not classificacao.somente_se_escolhido)

    provedores = await api.cliente.get("/v1/provedores", headers=auth)
    modelos_http = await api.cliente.get("/v1/modelos", headers=auth)
    assert provedores.status_code == 200
    assert [item["id"] for item in provedores.json()] == [provedor_id]
    assert modelos_http.status_code == 200
    assert [item["modelo"] for item in modelos_http.json()] == sorted(MODELOS_INICIAIS)

    modelos_por_nome = _por_modelo(modelos_http.json())
    luna_id = modelos_por_nome["openai/gpt-5.6-luna"]["id"]
    alterado = await api.cliente.patch(
        f"/v1/modelos/{luna_id}",
        json={"nivel": "especial", "ativo": False},
        headers=auth,
    )
    assert alterado.status_code == 200
    assert alterado.json()["nivel"] == "especial"
    assert alterado.json()["ativo"] is False
    async with api.fabrica() as sessao:
        luna = await sessao.get(ModeloDisponivel, luna_id)
    assert luna is not None
    assert luna.nivel == "especial"
    assert luna.ativo is False
    assert luna.origem == "usuario"

    com_teto = await api.cliente.patch(
        f"/v1/provedores/{provedor_id}",
        json={"teto_mensal_usd": "123.45"},
        headers=auth,
    )
    assert com_teto.status_code == 200
    assert Decimal(str(com_teto.json()["teto_mensal_usd"])) == Decimal("123.45")
    sem_teto = await api.cliente.patch(
        f"/v1/provedores/{provedor_id}", json={"teto_mensal_usd": None}, headers=auth
    )
    assert sem_teto.status_code == 200
    assert sem_teto.json()["teto_mensal_usd"] is None

    sincronizado = await api.cliente.patch(
        f"/v1/provedores/{provedor_id}", json={"chave": CHAVE_NOVA}, headers=auth
    )
    assert sincronizado.status_code == 200
    assert sincronizado.json()["chave_final"] == "4321"
    async with api.fabrica() as sessao:
        provedor = await sessao.get(Provedor, provedor_id)
        modelos_apos_sync = list(
            await sessao.scalars(
                select(ModeloDisponivel).where(ModeloDisponivel.provedor_id == provedor_id)
            )
        )
    assert provedor is not None and provedor.chave_cifrada is not None
    assert (
        decifrar_segredo(provedor.chave_cifrada, usuario_id=usuario_id, provedor=str(provedor.id))
        == CHAVE_NOVA
    )
    por_nome = {modelo.modelo: modelo for modelo in modelos_apos_sync}
    assert por_nome["openai/gpt-5.6-luna"].nivel == "especial"
    assert por_nome["openai/gpt-5.6-luna"].ativo is False
    assert por_nome["openai/gpt-5.6-luna"].origem == "usuario"
    assert por_nome["openai/gpt-5.6-sol"].nivel == "N3"
    assert por_nome["openai/gpt-5.6-sol"].ativo is True
    assert por_nome["openai/gpt-5.6-terra"].ativo is False
    assert por_nome["openai/modelo-fora-do-catalogo"].ativo is False

    estado_antes_da_falha = (
        provedor.chave_cifrada,
        provedor.chave_final,
        provedor.validado_em,
        sorted((modelo.modelo, modelo.nivel, modelo.ativo) for modelo in modelos_apos_sync),
    )
    falhou = await api.cliente.patch(
        f"/v1/provedores/{provedor_id}", json={"chave": CHAVE_COM_ERRO}, headers=auth
    )
    assert falhou.status_code == 422
    async with api.fabrica() as sessao:
        provedor_depois = await sessao.get(Provedor, provedor_id)
        modelos_depois = list(
            await sessao.scalars(
                select(ModeloDisponivel).where(ModeloDisponivel.provedor_id == provedor_id)
            )
        )
    assert provedor_depois is not None
    assert (
        provedor_depois.chave_cifrada,
        provedor_depois.chave_final,
        provedor_depois.validado_em,
        sorted((modelo.modelo, modelo.nivel, modelo.ativo) for modelo in modelos_depois),
    ) == estado_antes_da_falha

    preferencia = await api.cliente.patch(
        "/v1/preferencias", json={"prioridade": "qualidade"}, headers=auth
    )
    assert preferencia.status_code == 204
    eu = await api.cliente.get("/v1/eu", headers=auth)
    assert eu.status_code == 200
    assert eu.json()["prioridade"] == "qualidade"
    assert eu.json()["tem_provedor"] is True

    apagado = await api.cliente.delete(f"/v1/provedores/{provedor_id}", headers=auth)
    assert apagado.status_code == 204
    async with api.fabrica() as sessao:
        provedor_apagado = await sessao.get(Provedor, provedor_id)
        ativos = await sessao.scalar(
            select(func.count())
            .select_from(ModeloDisponivel)
            .where(
                ModeloDisponivel.provedor_id == provedor_id,
                ModeloDisponivel.ativo.is_(True),
            )
        )
    assert provedor_apagado is not None
    assert provedor_apagado.apagado_em is not None
    assert provedor_apagado.chave_cifrada is None
    assert provedor_apagado.chave_final is None
    assert ativos == 0
    assert (await api.cliente.get("/v1/provedores", headers=auth)).json() == []
    assert (await api.cliente.get("/v1/modelos", headers=auth)).json() == []
    assert (await api.cliente.get("/v1/eu", headers=auth)).json()["tem_provedor"] is False
    assert (
        await api.cliente.patch(
            f"/v1/provedores/{provedor_id}", json={"teto_mensal_usd": 1}, headers=auth
        )
    ).status_code == 404
    assert (
        await api.cliente.patch(f"/v1/modelos/{luna_id}", json={"ativo": True}, headers=auth)
    ).status_code == 404


async def test_erros_do_listador_e_lista_vazia_nao_gravam_nada(api: AmbienteAPI) -> None:
    auth = await _cadastrar_e_entrar(api.cliente)
    casos = [
        (CHAVE_INVALIDA, "O provedor recusou a chave."),
        (CHAVE_COM_ERRO, "Não foi possível conectar ao provedor."),
        (CHAVE_BLOQUEADA, "A URL da API aponta para a rede local, o que não é permitido."),
        (CHAVE_LISTA_VAZIA, "O provedor não devolveu nenhum modelo."),
    ]
    for chave, detalhe in casos:
        resposta = await api.cliente.post(
            "/v1/provedores", json={"tipo": "openai", "chave": chave}, headers=auth
        )
        assert resposta.status_code == 422
        assert resposta.json() == {"detail": detalhe}

    chamadas_antes = len(api.listador.chamadas)
    sem_chave = await api.cliente.post("/v1/provedores", json={"tipo": "openai"}, headers=auth)
    assert sem_chave.status_code == 422
    assert len(api.listador.chamadas) == chamadas_antes
    async with api.fabrica() as sessao:
        assert await sessao.scalar(select(func.count()).select_from(Provedor)) == 0
        assert await sessao.scalar(select(func.count()).select_from(ModeloDisponivel)) == 0


async def test_duplicado_normalizado_chave_curta_e_limites_do_teto(api: AmbienteAPI) -> None:
    auth = await _cadastrar_e_entrar(api.cliente)
    criado = await api.cliente.post(
        "/v1/provedores",
        json={
            "tipo": "compativel_openai",
            "chave": CHAVE_CURTA,
            "base_url": "https://93.184.216.34/v1/",
        },
        headers=auth,
    )
    assert criado.status_code == 201
    assert criado.json()["provedor"]["base_url"] == "https://93.184.216.34/v1"
    assert criado.json()["provedor"]["chave_final"] is None
    provedor_id = criado.json()["provedor"]["id"]

    duplicado = await api.cliente.post(
        "/v1/provedores",
        json={
            "tipo": "compativel_openai",
            "chave": CHAVE_CURTA,
            "base_url": "  https://93.184.216.34/v1///  ",
        },
        headers=auth,
    )
    assert duplicado.status_code == 409
    assert duplicado.json() == {"detail": "Essa API já está conectada."}

    for teto in ("-0.01", "100000.01"):
        invalido = await api.cliente.patch(
            f"/v1/provedores/{provedor_id}",
            json={"teto_mensal_usd": teto},
            headers=auth,
        )
        assert invalido.status_code == 422
    async with api.fabrica() as sessao:
        provedor = await sessao.get(Provedor, provedor_id)
    assert provedor is not None
    assert provedor.teto_mensal_usd is None


async def test_decimo_primeiro_provedor_recebe_409(api: AmbienteAPI) -> None:
    auth = await _cadastrar_e_entrar(api.cliente)
    usuario_id = await _usuario_id(api)
    async with api.fabrica() as sessao:
        sessao.add_all(
            [
                Provedor(
                    usuario_id=usuario_id,
                    tipo="compativel_openai",
                    base_url=f"https://93.184.216.{indice}/v1",
                    chave_cifrada=None,
                    chave_final=None,
                    validado_em=datetime.now(UTC),
                )
                for indice in range(1, 11)
            ]
        )
        await sessao.commit()

    resposta = await api.cliente.post(
        "/v1/provedores",
        json={
            "tipo": "compativel_openai",
            "base_url": "https://93.184.216.20/v1",
        },
        headers=auth,
    )
    assert resposta.status_code == 409
    assert resposta.json() == {"detail": "Você pode conectar no máximo 10 APIs."}
    async with api.fabrica() as sessao:
        assert await sessao.scalar(select(func.count()).select_from(Provedor)) == 10


async def test_duas_conexoes_simultaneas_no_nono_provedor_so_uma_entra(
    api: AmbienteAPI,
) -> None:
    auth = await _cadastrar_e_entrar(api.cliente)
    usuario_id = await _usuario_id(api)
    async with api.fabrica() as sessao:
        sessao.add_all(
            [
                Provedor(
                    usuario_id=usuario_id,
                    tipo="compativel_openai",
                    base_url=f"https://93.184.216.{indice}/v1",
                    chave_cifrada=None,
                    chave_final=None,
                    validado_em=datetime.now(UTC),
                )
                for indice in range(1, 10)
            ]
        )
        await sessao.commit()

    respostas = await asyncio.gather(
        api.cliente.post(
            "/v1/provedores",
            json={"tipo": "openai", "chave": CHAVE_ORIGINAL},
            headers=auth,
        ),
        api.cliente.post(
            "/v1/provedores",
            json={"tipo": "compativel_openai", "base_url": "https://93.184.216.30/v1"},
            headers=auth,
        ),
    )
    codigos = sorted(resposta.status_code for resposta in respostas)
    assert codigos == [201, 409]
    recusada = next(resposta for resposta in respostas if resposta.status_code == 409)
    assert recusada.json() == {"detail": "Você pode conectar no máximo 10 APIs."}
    async with api.fabrica() as sessao:
        total = await sessao.scalar(
            select(func.count())
            .select_from(Provedor)
            .where(Provedor.usuario_id == usuario_id, Provedor.apagado_em.is_(None))
        )
    assert total == 10


async def test_outro_usuario_recebe_404_e_nao_enxerga_dados(api: AmbienteAPI) -> None:
    auth_ana = await _cadastrar_e_entrar(api.cliente, "ana@exemplo.com")
    conexao = await api.cliente.post(
        "/v1/provedores",
        json={"tipo": "openai", "chave": CHAVE_ORIGINAL},
        headers=auth_ana,
    )
    assert conexao.status_code == 201
    provedor_id = conexao.json()["provedor"]["id"]
    modelo_id = conexao.json()["modelos"][0]["id"]

    auth_bia = await _cadastrar_e_entrar(api.cliente, "bia@exemplo.com")
    assert (await api.cliente.get("/v1/provedores", headers=auth_bia)).json() == []
    assert (await api.cliente.get("/v1/modelos", headers=auth_bia)).json() == []
    assert (
        await api.cliente.patch(
            f"/v1/provedores/{provedor_id}", json={"teto_mensal_usd": 10}, headers=auth_bia
        )
    ).status_code == 404
    assert (
        await api.cliente.delete(f"/v1/provedores/{provedor_id}", headers=auth_bia)
    ).status_code == 404
    assert (
        await api.cliente.patch(f"/v1/modelos/{modelo_id}", json={"nivel": "N3"}, headers=auth_bia)
    ).status_code == 404


async def test_limite_de_dez_testes_de_chave_por_hora(api: AmbienteAPI) -> None:
    auth = await _cadastrar_e_entrar(api.cliente)
    for _ in range(10):
        resposta = await api.cliente.post(
            "/v1/provedores",
            json={"tipo": "openai", "chave": CHAVE_INVALIDA},
            headers=auth,
        )
        assert resposta.status_code == 422

    bloqueado = await api.cliente.post(
        "/v1/provedores",
        json={"tipo": "openai", "chave": CHAVE_INVALIDA},
        headers=auth,
    )
    assert bloqueado.status_code == 429
    assert int(bloqueado.headers["retry-after"]) > 0
    assert len(api.listador.chamadas) == 10


async def test_guarda_so_os_primeiros_500_modelos_em_ordem_alfabetica(
    api: AmbienteAPI,
) -> None:
    auth = await _cadastrar_e_entrar(api.cliente)
    devolvidos = [f"openai/modelo-{indice:03}" for indice in range(501, -1, -1)]
    api.listador.respostas[CHAVE_MUITOS_MODELOS] = devolvidos

    resposta = await api.cliente.post(
        "/v1/provedores",
        json={"tipo": "openai", "chave": CHAVE_MUITOS_MODELOS},
        headers=auth,
    )
    assert resposta.status_code == 201
    esperados = sorted(devolvidos)[:500]
    assert [item["modelo"] for item in resposta.json()["modelos"]] == esperados
    async with api.fabrica() as sessao:
        gravados = list(
            await sessao.scalars(select(ModeloDisponivel.modelo).order_by(ModeloDisponivel.modelo))
        )
    assert gravados == esperados
