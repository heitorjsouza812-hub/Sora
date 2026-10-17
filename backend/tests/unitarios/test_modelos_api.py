"""Etapa 1 (Catálogo): rotas /v1/modelos e /v1/preferencias, ``tem_provedor`` validado (regra
13), a 412 de ``exigir_provedor_validado`` (regra 14) e a ponte banco → seletor
(``app.seletor.repositorio``).

Duas partes: sessão falsa (roda sempre, confere regras e o SQL gerado) e PostgreSQL real
(marcados ``integracao``; pulam sozinhos sem Docker). Nenhum teste chama a internet.
"""

import asyncio
import base64
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from app.core import contas, seguranca
from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import exigir_provedor_validado, usuario_atual
from app.main import criar_aplicacao
from app.modelos.enumeracoes import Prioridade, TipoProvedor
from app.modelos.tabelas import ModeloDisponivel, Provedor, Usuario
from app.seletor import repositorio
from tests.integracao.conftest import docker_disponivel

CHAVE = "sk-TESTE-NAO-VAZAR-1234567890"
USUARIO = UUID("12121212-1212-4121-8121-121212121212")


def _sql(consulta: Any) -> str:
    return str(consulta.compile(dialect=postgresql.dialect())).lower()


# --------------------------------------------------------------------------- sessão falsa


class _Resultado:
    def __init__(self, itens: list[Any]) -> None:
        self._itens = itens

    def all(self) -> list[Any]:
        return list(self._itens)


class _SessaoFalsa:
    """Responde ``scalar``/``scalars``/``execute`` com filas prontas e guarda as consultas."""

    def __init__(
        self,
        *,
        scalar: list[Any] | None = None,
        scalars: list[list[Any]] | None = None,
        execute: list[list[Any]] | None = None,
    ) -> None:
        self._scalar = list(scalar or [])
        self._scalars = list(scalars or [])
        self._execute = list(execute or [])
        self.consultas: list[Any] = []
        self.flushes = 0

    async def scalar(self, consulta: Any) -> Any:
        self.consultas.append(consulta)
        return self._scalar.pop(0)

    async def scalars(self, consulta: Any) -> _Resultado:
        self.consultas.append(consulta)
        return _Resultado(self._scalars.pop(0))

    async def execute(self, consulta: Any) -> _Resultado:
        self.consultas.append(consulta)
        return _Resultado(self._execute.pop(0) if self._execute else [])

    async def flush(self) -> None:
        self.flushes += 1

    async def get(self, _tabela: Any, _id: Any) -> Any:
        return Usuario(id=USUARIO, email="ana@exemplo.com", nome="Ana", senha_hash="x")


def _modelo(nome: str = "groq/llama-a", **campos: Any) -> ModeloDisponivel:
    valores: dict[str, Any] = {
        "id": uuid4(),
        "provedor_id": uuid4(),
        "modelo": nome,
        "nivel": "N1",
        "capacidades": ["ferramentas"],
        "contexto": 128_000,
        "preco_entrada": Decimal("0.1"),
        "preco_saida": Decimal("0.2"),
        "velocidade_tps": 500,
        "origem": "catalogo",
        "ativo": True,
    }
    valores.update(campos)
    return ModeloDisponivel(**valores)


async def _cliente_falso(app: FastAPI, sessao: _SessaoFalsa) -> AsyncClient:
    async def sessao_dep() -> AsyncIterator[_SessaoFalsa]:
        yield sessao

    app.dependency_overrides[usuario_atual] = lambda: USUARIO
    app.dependency_overrides[obter_sessao] = sessao_dep
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://teste")


async def test_listar_modelos_filtra_dono_e_apagado_e_ordena(aplicacao: FastAPI) -> None:
    sessao = _SessaoFalsa(scalars=[[_modelo("groq/b"), _modelo("groq/a")]])
    async with await _cliente_falso(aplicacao, sessao) as c:
        resposta = await c.get("/v1/modelos")
    assert resposta.status_code == 200
    assert [m["modelo"] for m in resposta.json()] == ["groq/b", "groq/a"]  # ordem do banco
    sql = _sql(sessao.consultas[0])
    assert "provedores.usuario_id = " in sql
    assert "provedores.apagado_em is null" in sql
    assert sql.split("order by")[1].strip().startswith("provedores.criado_em")
    assert "modelos_disponiveis.modelo" in sql.split("order by")[1]


@pytest.mark.parametrize("corpo", [{"nivel": "N9"}, {"nivel": "n1"}, {"nivel": None}])
async def test_patch_nivel_invalido_responde_422_sem_tocar_no_banco(
    aplicacao: FastAPI, corpo: dict[str, Any]
) -> None:
    sessao = _SessaoFalsa()
    async with await _cliente_falso(aplicacao, sessao) as c:
        resposta = await c.patch(f"/v1/modelos/{uuid4()}", json=corpo)
    assert resposta.status_code == 422
    assert sessao.consultas == []


async def test_patch_ativo_nulo_responde_422(aplicacao: FastAPI) -> None:
    sessao = _SessaoFalsa()
    async with await _cliente_falso(aplicacao, sessao) as c:
        resposta = await c.patch(f"/v1/modelos/{uuid4()}", json={"ativo": None})
    assert resposta.status_code == 422


async def test_patch_modelo_alheio_ou_inexistente_responde_404(aplicacao: FastAPI) -> None:
    sessao = _SessaoFalsa(scalar=[None])
    async with await _cliente_falso(aplicacao, sessao) as c:
        resposta = await c.patch(f"/v1/modelos/{uuid4()}", json={"ativo": False})
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Modelo não encontrado."
    sql = _sql(sessao.consultas[0])
    assert "provedores.usuario_id = " in sql and "provedores.apagado_em is null" in sql
    assert "for update of modelos_disponiveis" in sql


async def test_patch_mudar_nivel_grava_origem_usuario(aplicacao: FastAPI) -> None:
    modelo = _modelo(nivel="N1")
    sessao = _SessaoFalsa(scalar=[modelo])
    async with await _cliente_falso(aplicacao, sessao) as c:
        resposta = await c.patch(f"/v1/modelos/{modelo.id}", json={"nivel": "especial"})
    assert resposta.status_code == 200
    assert resposta.json()["nivel"] == "especial"
    assert modelo.origem == "usuario"
    assert sessao.flushes == 1


async def test_patch_so_ativo_ou_mesmo_nivel_mantem_origem(aplicacao: FastAPI) -> None:
    modelo = _modelo(nivel="N2", ativo=True)
    sessao = _SessaoFalsa(scalar=[modelo, modelo])
    async with await _cliente_falso(aplicacao, sessao) as c:
        r1 = await c.patch(f"/v1/modelos/{modelo.id}", json={"ativo": False})
        r2 = await c.patch(f"/v1/modelos/{modelo.id}", json={"nivel": "N2"})
    assert r1.status_code == r2.status_code == 200
    assert modelo.ativo is False
    assert modelo.origem == "catalogo"


async def test_preferencias_atualiza_prioridade_do_usuario(aplicacao: FastAPI) -> None:
    sessao = _SessaoFalsa()
    async with await _cliente_falso(aplicacao, sessao) as c:
        resposta = await c.patch("/v1/preferencias", json={"prioridade": "qualidade"})
        invalida = await c.patch("/v1/preferencias", json={"prioridade": "barato"})
    assert resposta.status_code == 204
    assert invalida.status_code == 422
    assert len(sessao.consultas) == 1
    consulta = sessao.consultas[0]
    assert "update usuarios set prioridade" in _sql(consulta)
    assert consulta.compile().params["id_1"] == USUARIO


async def test_tem_provedor_exige_validado_e_nao_apagado() -> None:
    sessao = _SessaoFalsa(scalar=[None])
    _, tem = await contas.dados_da_conta(sessao, USUARIO)  # type: ignore[arg-type]
    assert tem is False
    sql = _sql(sessao.consultas[0])
    assert "provedores.validado_em is not null" in sql
    assert "provedores.apagado_em is null" in sql
    assert "provedores.usuario_id = " in sql


async def test_exigir_provedor_validado_responde_412_ou_libera(aplicacao: FastAPI) -> None:
    @aplicacao.get("/teste/precisa-provedor")
    async def rota(
        usuario_id: Annotated[UUID, Depends(exigir_provedor_validado)],
    ) -> dict[str, str]:
        return {"usuario": str(usuario_id)}

    sessao = _SessaoFalsa(scalar=[None, uuid4()])
    async with await _cliente_falso(aplicacao, sessao) as c:
        sem = await c.get("/teste/precisa-provedor")
        com = await c.get("/teste/precisa-provedor")
    assert sem.status_code == 412
    assert sem.json()["detail"] == "Conecte uma API de modelos antes de fazer pedidos."
    assert com.status_code == 200 and com.json() == {"usuario": str(USUARIO)}
    assert "provedores.validado_em is not null" in _sql(sessao.consultas[0])


def _provedor(**campos: Any) -> Provedor:
    valores: dict[str, Any] = {
        "id": uuid4(),
        "usuario_id": USUARIO,
        "tipo": TipoProvedor.ANTHROPIC,
        "base_url": None,
        "teto_mensal_usd": None,
        "pausado_ate": None,
        "validado_em": datetime.now(UTC),
    }
    valores.update(campos)
    return Provedor(**valores)


async def test_contexto_do_usuario_monta_candidatos(monkeypatch: pytest.MonkeyPatch) -> None:
    pausa = datetime.now(UTC) + timedelta(minutes=5)
    provedor = _provedor(teto_mensal_usd=Decimal("10"), pausado_ate=pausa)
    fable = _modelo("anthropic/claude-fable-5-1", provedor_id=provedor.id, nivel="N3", ativo=False)
    haiku = _modelo(
        "anthropic/claude-haiku-5-5",
        provedor_id=provedor.id,
        capacidades=["ferramentas", "visao", "coisa-nova"],
    )

    async def gasto(_sessao: Any, usuario_id: UUID) -> dict[UUID, Decimal]:
        assert usuario_id == USUARIO
        return {provedor.id: Decimal("12.5")}

    monkeypatch.setattr(repositorio, "gasto_do_mes_por_provedor", gasto)
    sessao = _SessaoFalsa(
        scalar=[Prioridade.QUALIDADE], execute=[[(fable, provedor), (haiku, provedor)]]
    )
    contexto = await repositorio.contexto_do_usuario(
        sessao,  # type: ignore[arg-type]
        USUARIO,
        conversa_privada=True,
    )
    assert contexto.prioridade is Prioridade.QUALIDADE
    assert contexto.conversa_privada is True
    assert [m.modelo for m in contexto.modelos] == [fable.modelo, haiku.modelo]
    assert [m.modelo for m in contexto.modelos_ativos()] == [haiku.modelo]
    assert contexto.modelos[0].somente_se_escolhido is True
    assert contexto.modelos[1].somente_se_escolhido is False
    assert {c.value for c in contexto.modelos[1].capacidades} == {"ferramentas", "visao"}
    seletor_prov = contexto.modelos[0].provedor
    assert seletor_prov is contexto.modelos[1].provedor  # um ProvedorSeletor por provedor
    assert seletor_prov.gasto_mes_usd == Decimal("12.5")
    assert seletor_prov.passou_do_teto() and seletor_prov.em_pausa(datetime.now(UTC))
    sql = _sql(sessao.consultas[1])
    assert "provedores.validado_em is not null" in sql
    assert "provedores.apagado_em is null" in sql
    assert "provedores.usuario_id = " in sql


async def test_contexto_sem_modelos_nao_consulta_gasto(monkeypatch: pytest.MonkeyPatch) -> None:
    async def gasto(*_: Any) -> dict[UUID, Decimal]:
        raise AssertionError("não devia consultar o gasto")

    monkeypatch.setattr(repositorio, "gasto_do_mes_por_provedor", gasto)
    sessao = _SessaoFalsa(scalar=[None], execute=[[]])
    contexto = await repositorio.contexto_do_usuario(sessao, USUARIO)  # type: ignore[arg-type]
    assert contexto.modelos == [] and contexto.prioridade is Prioridade.CUSTO


async def test_config_do_provedor_decifra_com_aad_da_linha() -> None:
    provedor = _provedor(base_url=None)
    provedor.chave_cifrada = seguranca.cifrar_segredo(
        CHAVE, usuario_id=USUARIO, provedor=str(provedor.id)
    )
    sessao = _SessaoFalsa(scalar=[provedor])
    config = await repositorio.config_do_provedor(
        sessao,  # type: ignore[arg-type]
        USUARIO,
        provedor.id,
    )
    assert config.api_key is not None and config.api_key.get_secret_value() == CHAVE
    assert config.provedor_id == provedor.id and config.tipo is TipoProvedor.ANTHROPIC
    assert CHAVE not in repr(config) and CHAVE not in str(config)
    assert sessao.flushes == 0  # chave já na versão atual: não regrava
    sql = _sql(sessao.consultas[0])
    assert "provedores.usuario_id = " in sql and "provedores.apagado_em is null" in sql


async def test_config_do_provedor_sem_chave_e_inexistente() -> None:
    ollama = _provedor(tipo=TipoProvedor.OLLAMA, base_url="http://ollama:11434")
    ollama.chave_cifrada = None
    sessao = _SessaoFalsa(scalar=[ollama, None])
    config = await repositorio.config_do_provedor(sessao, USUARIO, ollama.id)  # type: ignore[arg-type]
    assert config.api_key is None and config.base_url == "http://ollama:11434"
    with pytest.raises(LookupError):
        await repositorio.config_do_provedor(sessao, USUARIO, uuid4())  # type: ignore[arg-type]


async def test_config_do_provedor_aad_de_outra_linha_nao_decifra() -> None:
    provedor = _provedor()
    provedor.chave_cifrada = seguranca.cifrar_segredo(
        CHAVE, usuario_id=USUARIO, provedor=str(uuid4())
    )
    sessao = _SessaoFalsa(scalar=[provedor])
    with pytest.raises(Exception) as erro:
        await repositorio.config_do_provedor(sessao, USUARIO, provedor.id)  # type: ignore[arg-type]
    assert CHAVE not in str(erro.value)


@pytest.fixture
def chave_mestra_rotacionada(monkeypatch: pytest.MonkeyPatch):
    """Troca a chave mestra para a versão 2, mantendo a 1 só para decifrar."""

    def girar() -> None:
        monkeypatch.setenv("CHAVES_MESTRAS_ANTIGAS", f"1:{os.environ['CHAVE_MESTRA']}")
        monkeypatch.setenv("CHAVE_MESTRA", base64.b64encode(b"N" * 32).decode())
        monkeypatch.setenv("CHAVE_MESTRA_VERSAO", "2")
        obter_configuracao.cache_clear()

    obter_configuracao.cache_clear()
    yield girar
    obter_configuracao.cache_clear()


async def test_config_do_provedor_recifra_chave_antiga(chave_mestra_rotacionada) -> None:
    provedor = _provedor()
    provedor.chave_cifrada = seguranca.cifrar_segredo(
        CHAVE, usuario_id=USUARIO, provedor=str(provedor.id)
    )
    assert provedor.chave_cifrada[0] == 1
    chave_mestra_rotacionada()
    sessao = _SessaoFalsa(scalar=[provedor])
    config = await repositorio.config_do_provedor(sessao, USUARIO, provedor.id)  # type: ignore[arg-type]
    assert config.api_key is not None and config.api_key.get_secret_value() == CHAVE
    assert provedor.chave_cifrada[0] == 2
    assert sessao.flushes == 1


# --------------------------------------------------------------------- PostgreSQL real

_DOCKER, _MOTIVO = docker_disponivel()
sem_docker = pytest.mark.skipif(not _DOCKER, reason=_MOTIVO)
RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def postgres():
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture
async def banco(postgres: str, monkeypatch: pytest.MonkeyPatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    monkeypatch.setenv("DATABASE_URL", postgres)
    config = Config(str(RAIZ / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ / "migrations"))
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(command.upgrade, config, "head")
    motor = create_async_engine(postgres)
    yield async_sessionmaker(motor, expire_on_commit=False)
    await motor.dispose()


class _Cenario:
    """Dois usuários e provedores em todos os estados (validado, sem validar, apagado)."""

    def __init__(self) -> None:
        self.ana = uuid4()
        self.beto = uuid4()
        self.caio = uuid4()  # só tem provedor sem validar e provedor validado apagado
        self.agora = datetime.now(UTC)


async def _montar(fabrica: Any) -> tuple[_Cenario, dict[str, Provedor], dict[str, UUID]]:
    from app.modelos.tabelas import ChamadaModelo

    c = _Cenario()
    t = c.agora - timedelta(days=1)
    provs = {
        "groq": _provedor(
            usuario_id=c.ana, tipo=TipoProvedor.GROQ, criado_em=t, teto_mensal_usd=Decimal(5)
        ),
        "anthropic": _provedor(usuario_id=c.ana, criado_em=t + timedelta(hours=1)),
        "openai_apagado": _provedor(
            usuario_id=c.ana,
            tipo=TipoProvedor.OPENAI,
            criado_em=t + timedelta(hours=2),
            apagado_em=c.agora,
        ),
        "openrouter_sem_validar": _provedor(
            usuario_id=c.ana,
            tipo=TipoProvedor.OPENROUTER,
            criado_em=t + timedelta(hours=3),
            validado_em=None,
        ),
        "beto": _provedor(usuario_id=c.beto, tipo=TipoProvedor.GROQ, criado_em=t),
        "caio_sem_validar": _provedor(usuario_id=c.caio, validado_em=None, criado_em=t),
        "caio_apagado": _provedor(usuario_id=c.caio, apagado_em=c.agora, criado_em=t),
    }
    for p in provs.values():
        p.chave_cifrada = seguranca.cifrar_segredo(
            CHAVE, usuario_id=p.usuario_id, provedor=str(p.id)
        )
        p.chave_final = CHAVE[-4:]
    nomes = {
        "llama_b": ("groq", "groq/llama-b"),
        "llama_a": ("groq", "groq/llama-a"),
        "fable": ("anthropic", "anthropic/claude-fable-5-1"),
        "haiku": ("anthropic", "anthropic/claude-haiku-5-5"),
        "apagado": ("openai_apagado", "openai/gpt-x"),
        "sem_validar": ("openrouter_sem_validar", "openrouter/y"),
        "beto": ("beto", "groq/z"),
    }
    modelos = {
        k: _modelo(nome, provedor_id=provs[p].id, ativo=k != "fable")
        for k, (p, nome) in nomes.items()
    }
    async with fabrica() as s:
        for uid, email in ((c.ana, "ana"), (c.beto, "beto"), (c.caio, "caio")):
            s.add(Usuario(id=uid, email=f"{email}@exemplo.com", nome=email, senha_hash="x"))
        await s.flush()
        s.add_all(provs.values())
        await s.flush()
        s.add_all(modelos.values())
        s.add(
            ChamadaModelo(
                usuario_id=c.ana,
                provedor_id=provs["groq"].id,
                papel="sora",
                modelo="groq/llama-a",
                nivel="N1",
                tokens_entrada=10,
                tokens_saida=10,
                custo_usd=Decimal("7.25"),
                latencia_ms=100,
            )
        )
        await s.commit()
    return c, provs, {k: m.id for k, m in modelos.items()}


async def _cliente_real(fabrica: Any) -> tuple[FastAPI, AsyncClient]:
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
    return app, AsyncClient(transport=ASGITransport(app=app), base_url="http://teste")


def _auth(usuario_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {seguranca.criar_token_acesso({'sub': str(usuario_id)})}"}


@pytest.mark.integracao
@sem_docker
async def test_pg_listar_e_atualizar_modelos(banco: Any) -> None:
    c, _provs, ids = await _montar(banco)
    _, cliente = await _cliente_real(banco)
    async with cliente:
        lista = await cliente.get("/v1/modelos", headers=_auth(c.ana))
        assert lista.status_code == 200
        assert CHAVE not in lista.text
        assert [m["modelo"] for m in lista.json()] == [
            "groq/llama-a",
            "groq/llama-b",
            "anthropic/claude-fable-5-1",
            "anthropic/claude-haiku-5-5",
            "openrouter/y",
        ]
        # Regra 9: alheio, de provedor apagado ou inexistente → 404 igual.
        for alvo in (ids["beto"], ids["apagado"], uuid4()):
            r = await cliente.patch(
                f"/v1/modelos/{alvo}", headers=_auth(c.ana), json={"ativo": False}
            )
            assert r.status_code == 404 and r.json()["detail"] == "Modelo não encontrado."
        r = await cliente.patch(
            f"/v1/modelos/{ids['llama_a']}", headers=_auth(c.ana), json={"nivel": "N9"}
        )
        assert r.status_code == 422
        r = await cliente.patch(
            f"/v1/modelos/{ids['llama_a']}",
            headers=_auth(c.ana),
            json={"nivel": "N3", "ativo": False},
        )
        assert r.status_code == 200
        assert r.json()["nivel"] == "N3" and r.json()["ativo"] is False
    async with banco() as s:
        llama = await s.get(ModeloDisponivel, ids["llama_a"])
        beto = await s.get(ModeloDisponivel, ids["beto"])
    assert (llama.nivel, llama.origem, llama.ativo) == ("N3", "usuario", False)
    assert beto.ativo is True


@pytest.mark.integracao
@sem_docker
async def test_pg_preferencias_eu_e_412(banco: Any) -> None:
    c, _provs, _ = await _montar(banco)
    app, cliente = await _cliente_real(banco)

    @app.get("/teste/precisa-provedor")
    async def rota(
        usuario_id: Annotated[UUID, Depends(exigir_provedor_validado)],
    ) -> dict[str, str]:
        return {"usuario": str(usuario_id)}

    async with cliente:
        r = await cliente.patch(
            "/v1/preferencias", headers=_auth(c.ana), json={"prioridade": "velocidade"}
        )
        assert r.status_code == 204
        eu_ana = (await cliente.get("/v1/eu", headers=_auth(c.ana))).json()
        eu_caio = (await cliente.get("/v1/eu", headers=_auth(c.caio))).json()
        assert eu_ana["prioridade"] == "velocidade" and eu_ana["tem_provedor"] is True
        assert eu_caio["prioridade"] == "custo" and eu_caio["tem_provedor"] is False
        assert (
            await cliente.get("/teste/precisa-provedor", headers=_auth(c.ana))
        ).status_code == 200
        caio = await cliente.get("/teste/precisa-provedor", headers=_auth(c.caio))
        assert caio.status_code == 412
        assert caio.json()["detail"] == "Conecte uma API de modelos antes de fazer pedidos."


@pytest.mark.integracao
@sem_docker
async def test_pg_contexto_e_config_do_provedor(banco: Any, chave_mestra_rotacionada) -> None:
    c, provs, _ = await _montar(banco)
    async with banco() as s:
        contexto = await repositorio.contexto_do_usuario(s, c.ana)
    assert [m.modelo for m in contexto.modelos] == [
        "groq/llama-a",
        "groq/llama-b",
        "anthropic/claude-fable-5-1",
        "anthropic/claude-haiku-5-5",
    ]  # sem o apagado e sem o que não foi validado
    groq = contexto.modelos[0].provedor
    assert groq.gasto_mes_usd == Decimal("7.25") and groq.teto_mensal_usd == Decimal(5)
    assert groq.passou_do_teto()
    assert contexto.modelos[2].somente_se_escolhido and not contexto.modelos[2].ativo
    assert contexto.prioridade is Prioridade.CUSTO

    async with banco() as s:
        config = await repositorio.config_do_provedor(s, c.ana, provs["anthropic"].id)
        assert config.api_key is not None and config.api_key.get_secret_value() == CHAVE
        for alheio in (provs["beto"].id, provs["openai_apagado"].id, uuid4()):
            with pytest.raises(LookupError):
                await repositorio.config_do_provedor(s, c.ana, alheio)

    # Rotação: a chave antiga é regravada com a atual na primeira leitura.
    chave_mestra_rotacionada()
    async with banco() as s:
        config = await repositorio.config_do_provedor(s, c.ana, provs["groq"].id)
        await s.commit()
    assert config.api_key is not None and config.api_key.get_secret_value() == CHAVE
    async with banco() as s:
        gravada = await s.get(Provedor, provs["groq"].id)
    assert gravada.chave_cifrada is not None and gravada.chave_cifrada[0] == 2
