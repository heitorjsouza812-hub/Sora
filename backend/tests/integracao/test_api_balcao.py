"""Rotas do Balcão (entregas, perguntas, aprovações, agentes, anexos, uso); banco real."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import aprovacoes as api_aprovacoes
from app.api import perguntas as api_perguntas
from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis
from app.main import criar_aplicacao
from app.modelos.enumeracoes import (
    AutorMensagem,
    StatusAprovacao,
    StatusEtapa,
    TipoAgente,
    TipoEntrega,
)
from app.modelos.tabelas import (
    Agente,
    Aprovacao,
    Cadeia,
    ChamadaModelo,
    Conversa,
    Entrega,
    Etapa,
    Mensagem,
    Pergunta,
    Provedor,
    RegraPermissao,
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
    app.dependency_overrides[api_perguntas.obter_fila] = lambda: fila
    app.dependency_overrides[api_aprovacoes.obter_fila] = lambda: fila
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


async def _cena(api: Ambiente, usuario_id: UUID, status: StatusEtapa) -> Cena:
    async with api.fabrica() as sessao:
        sora = await sessao.scalar(
            select(Agente).where(Agente.usuario_id == usuario_id, Agente.tipo == TipoAgente.SORA)
        )
        assert sora is not None
        especialista = Agente(
            usuario_id=usuario_id, tipo=TipoAgente.ESPECIALISTA, nome="Atlas", cor="#56A8FF"
        )
        conversa = Conversa(usuario_id=usuario_id, agente_id=sora.id)
        sessao.add_all([especialista, conversa])
        await sessao.flush()
        mensagem = Mensagem(
            conversa_id=conversa.id, autor=AutorMensagem.USUARIO, conteudo="crie uma campanha"
        )
        sessao.add(mensagem)
        await sessao.flush()
        cadeia = Cadeia(
            usuario_id=usuario_id,
            conversa_id=conversa.id,
            pedido_id=mensagem.id,
            orcamento_tokens=1000,
        )
        sessao.add(cadeia)
        await sessao.flush()
        etapa = Etapa(
            cadeia_id=cadeia.id,
            ordem=1,
            especialista="pesquisador",
            agente_id=especialista.id,
            nivel="N2",
            tarefa="pesquisar",
            status=status,
        )
        sessao.add(etapa)
        await sessao.commit()
        return Cena(conversa.id, cadeia.id, etapa.id, especialista.id)


async def test_entregas_versoes_e_isolamento(api: Ambiente) -> None:
    auth, uid = await _entrar(api, "ana@exemplo.com")
    outro, _ = await _entrar(api, "bia@exemplo.com")
    cena = await _cena(api, uid, StatusEtapa.CONCLUIDA)
    async with api.fabrica() as sessao:
        for versao, titulo in ((1, "v1"), (2, "v2"), (2, "v2 b")):
            sessao.add(
                Entrega(
                    usuario_id=uid,
                    conversa_id=cena.conversa_id,
                    cadeia_id=cena.cadeia_id,
                    etapa_id=cena.etapa_id,
                    agente_id=cena.agente_id,
                    versao=versao,
                    tipo=TipoEntrega.TEXTO,
                    titulo=titulo,
                    resumo="r",
                    conteudo={"texto": titulo},
                )
            )
        await sessao.commit()
    url = f"/v1/conversas/{cena.conversa_id}/entregas"
    nova = (await api.cliente.get(url, headers=auth)).json()
    assert nova["versoes"] == [1, 2]
    assert sorted(e["titulo"] for e in nova["entregas"]) == ["v2", "v2 b"]
    antiga = (await api.cliente.get(url, params={"versao": 1}, headers=auth)).json()
    assert [e["titulo"] for e in antiga["entregas"]] == ["v1"]
    assert (await api.cliente.get(url, params={"versao": 9}, headers=auth)).status_code == 404
    assert (await api.cliente.get(url, headers=outro)).status_code == 404
    vazia = await _cena(api, uid, StatusEtapa.PENDENTE)
    corpo = (
        await api.cliente.get(f"/v1/conversas/{vazia.conversa_id}/entregas", headers=auth)
    ).json()
    assert corpo == {"entregas": [], "versoes": []}


async def test_pergunta_registra_e_retoma_a_etapa_uma_vez(api: Ambiente) -> None:
    auth, uid = await _entrar(api, "ana@exemplo.com")
    outro, _ = await _entrar(api, "bia@exemplo.com")
    cena = await _cena(api, uid, StatusEtapa.AGUARDANDO_USUARIO)
    async with api.fabrica() as sessao:
        pergunta = Pergunta(
            conversa_id=cena.conversa_id,
            cadeia_id=cena.cadeia_id,
            texto="Qual tom?",
            opcoes=[{"rotulo": "Leve", "valor": "leve"}, {"rotulo": "Formal", "valor": "formal"}],
        )
        sessao.add(pergunta)
        await sessao.commit()
        pid = pergunta.id
    url = f"/v1/perguntas/{pid}/responder"
    assert (await api.cliente.post(url, json={"valor": "leve"}, headers=outro)).status_code == 404
    assert (await api.cliente.post(url, json={"valor": "xyz"}, headers=auth)).status_code == 422
    assert api.fila.jobs == []
    assert (await api.cliente.post(url, json={"valor": "leve"}, headers=auth)).status_code == 204
    assert api.fila.jobs == [
        (
            "executar_etapa",
            (str(cena.etapa_id), {"pergunta_id": str(pid), "valor": "leve"}),
            {"_job_id": f"pergunta:{pid}"},
        )
    ]
    async with api.fabrica() as sessao:
        gravada = await sessao.get(Pergunta, pid)
    assert gravada is not None and gravada.resposta == "leve" and gravada.respondida_em
    assert (await api.cliente.post(url, json={"valor": "leve"}, headers=auth)).status_code == 409
    assert len(api.fila.jobs) == 1


async def test_pergunta_respondida_com_etapa_executando_sempre_cria_retomada(
    api: Ambiente,
) -> None:
    """B-N1: resposta no mesmo instante do cartao nao pode se perder antes da pausa."""
    auth, uid = await _entrar(api, "corrida-pergunta@exemplo.com")
    cena = await _cena(api, uid, StatusEtapa.EXECUTANDO)
    async with api.fabrica() as sessao:
        pergunta = Pergunta(
            conversa_id=cena.conversa_id,
            cadeia_id=cena.cadeia_id,
            texto="Qual tom?",
            opcoes=[
                {"rotulo": "Leve", "valor": "leve"},
                {"rotulo": "Formal", "valor": "formal"},
            ],
        )
        sessao.add(pergunta)
        await sessao.flush()
        etapa = await sessao.get(Etapa, cena.etapa_id)
        assert etapa is not None
        etapa.saida = {"pergunta_id": str(pergunta.id)}
        await sessao.commit()
        pergunta_id = pergunta.id

    resposta = await api.cliente.post(
        f"/v1/perguntas/{pergunta_id}/responder",
        json={"valor": "formal"},
        headers=auth,
    )
    assert resposta.status_code == 204
    assert api.fila.jobs == [
        (
            "executar_etapa",
            (str(cena.etapa_id), {"pergunta_id": str(pergunta_id), "valor": "formal"}),
            {"_job_id": f"pergunta:{pergunta_id}"},
        )
    ]


async def _aprovacao(api: Ambiente, uid: UUID, cena: Cena, expira: timedelta) -> UUID:
    async with api.fabrica() as sessao:
        aprovacao = Aprovacao(
            usuario_id=uid,
            etapa_id=cena.etapa_id,
            agente_id=cena.agente_id,
            acao={"ferramenta": "enviar_email", "condicao": {"dominio": "x.com"}},
            avaliacao={"dano": "baixo"},
            expira_em=datetime.now(UTC) + expira,
        )
        sessao.add(aprovacao)
        await sessao.commit()
        return aprovacao.id


async def test_aprovacao_sempre_permitir_cria_regra_publica_evento_e_retoma(api: Ambiente) -> None:
    auth, uid = await _entrar(api, "ana@exemplo.com")
    outro, _ = await _entrar(api, "bia@exemplo.com")
    cena = await _cena(api, uid, StatusEtapa.AGUARDANDO_APROVACAO)
    aid = await _aprovacao(api, uid, cena, timedelta(minutes=5))
    url = f"/v1/aprovacoes/{aid}/decidir"
    corpo = {"decisao": "sempre_permitir"}
    assert (await api.cliente.post(url, json=corpo, headers=outro)).status_code == 404
    assert (await api.cliente.post(url, json=corpo, headers=auth)).status_code == 204
    async with api.fabrica() as sessao:
        aprovacao = await sessao.get(Aprovacao, aid)
        regras = list(await sessao.scalars(select(RegraPermissao)))
    assert aprovacao is not None and aprovacao.status == StatusAprovacao.PERMITIDA
    assert [(r.ferramenta, r.agente_id, r.condicao) for r in regras] == [
        ("enviar_email", cena.agente_id, {"dominio": "x.com"})
    ]
    assert api.fila.jobs[0][0:2] == (
        "executar_etapa",
        (str(cena.etapa_id), {"aprovacao_id": str(aid), "decisao": "sempre_permitir"}),
    )
    eventos = await api.redis.xrange(f"eventos:{cena.conversa_id}")
    assert [e[1]["event"] for e in eventos] == ["aprovacao.resolvida"]
    assert (await api.cliente.post(url, json=corpo, headers=auth)).status_code == 409


async def test_aprovacao_negada_nao_cria_regra_e_expirada_recusa(api: Ambiente) -> None:
    auth, uid = await _entrar(api, "ana@exemplo.com")
    cena = await _cena(api, uid, StatusEtapa.AGUARDANDO_APROVACAO)
    aid = await _aprovacao(api, uid, cena, timedelta(minutes=5))
    r = await api.cliente.post(
        f"/v1/aprovacoes/{aid}/decidir", json={"decisao": "negar"}, headers=auth
    )
    assert r.status_code == 204
    async with api.fabrica() as sessao:
        aprovacao = await sessao.get(Aprovacao, aid)
        assert list(await sessao.scalars(select(RegraPermissao))) == []
    assert aprovacao is not None and aprovacao.status == StatusAprovacao.NEGADA
    vencida = await _aprovacao(api, uid, cena, timedelta(seconds=-1))
    r = await api.cliente.post(
        f"/v1/aprovacoes/{vencida}/decidir", json={"decisao": "permitir_uma_vez"}, headers=auth
    )
    assert r.status_code == 409


async def test_agentes_limite_promocao_edicao_e_exclusao(api: Ambiente) -> None:
    auth, uid = await _entrar(api, "ana@exemplo.com")
    outro, _ = await _entrar(api, "bia@exemplo.com")
    primeiro = await api.cliente.post(
        "/v1/agentes",
        json={"descricao": "Pesquise concorrentes toda semana. Resuma."},
        headers=auth,
    )
    assert primeiro.status_code == 201
    agente = primeiro.json()
    assert agente["tipo"] == "individual" and agente["cor"] != "#E2ECFF"
    assert agente["funcao"] == "Pesquise concorrentes toda semana"
    configurado = await api.cliente.post(
        "/v1/agentes",
        json={"nome": "Rita", "funcao": "Redatora", "papel": "Escreve", "cor": "#46e8a8"},
        headers=auth,
    )
    assert configurado.status_code == 201 and configurado.json()["cor"] == "#46E8A8"
    for corpo in (
        {"nome": "Sora", "funcao": "x", "papel": "y"},
        {"nome": "Rita", "funcao": "x", "papel": "y"},
        {"nome": "Zé", "funcao": "x", "papel": "y", "cor": "#e2ecff"},
        {"nome": "Zé", "funcao": "x", "papel": "y", "ferramentas": ["apagar_tudo"]},
    ):
        r = await api.cliente.post("/v1/agentes", json=corpo, headers=auth)
        assert r.status_code in (409, 422), corpo
    for i in range(3):
        assert (
            await api.cliente.post("/v1/agentes", json={"descricao": f"Agente {i}"}, headers=auth)
        ).status_code == 201
    cheio = await api.cliente.post("/v1/agentes", json={"descricao": "mais um"}, headers=auth)
    assert cheio.status_code == 409

    lista = await api.cliente.get("/v1/agentes", params={"tipo": "individual"}, headers=auth)
    assert len(lista.json()) == 5
    assert (await api.cliente.get("/v1/agentes", headers=outro)).json()[0]["tipo"] == "sora"
    sora = next(
        a
        for a in (await api.cliente.get("/v1/agentes", headers=auth)).json()
        if a["tipo"] == "sora"
    )
    assert (
        await api.cliente.patch(f"/v1/agentes/{sora['id']}", json={"nome": "X"}, headers=auth)
    ).status_code == 409
    assert (await api.cliente.delete(f"/v1/agentes/{sora['id']}", headers=auth)).status_code == 409

    editado = await api.cliente.patch(
        f"/v1/agentes/{agente['id']}",
        json={"nome": "Luma", "movimento": "ondas", "modelo_padrao": "groq/x"},
        headers=auth,
    )
    assert editado.status_code == 200 and editado.json()["nome"] == "Luma"
    assert (
        await api.cliente.patch(f"/v1/agentes/{agente['id']}", json={"nome": "Rita"}, headers=auth)
    ).status_code == 409
    assert (
        await api.cliente.patch(f"/v1/agentes/{agente['id']}", json={"nome": "A"}, headers=outro)
    ).status_code == 404

    cena = await _cena(api, uid, StatusEtapa.EXECUTANDO)
    assert (
        await api.cliente.post(f"/v1/agentes/{cena.agente_id}/promover", headers=auth)
    ).status_code == 409
    assert (
        await api.cliente.delete(f"/v1/agentes/{agente['id']}", headers=outro)
    ).status_code == 404
    assert (
        await api.cliente.delete(f"/v1/agentes/{agente['id']}", headers=auth)
    ).status_code == 204
    promovido = await api.cliente.post(f"/v1/agentes/{cena.agente_id}/promover", headers=auth)
    assert promovido.status_code == 200 and promovido.json()["tipo"] == "individual"
    ativos = await api.cliente.get("/v1/agentes", params={"tipo": "individual"}, headers=auth)
    assert len(ativos.json()) == 5
    assert (
        await api.cliente.delete(f"/v1/agentes/{agente['id']}", headers=auth)
    ).status_code == 404


async def test_anexos_envio_download_e_recusas(api: Ambiente, tmp_path: Path) -> None:
    auth, _ = await _entrar(api, "ana@exemplo.com")
    outro, _ = await _entrar(api, "bia@exemplo.com")
    ok = await api.cliente.post(
        "/v1/anexos", files={"arquivo": ("logo.png", PNG, "text/html")}, headers=auth
    )
    assert ok.status_code == 201
    corpo = ok.json()
    assert corpo["nome"] == "logo.png" and corpo["tipo"] == "image/png"
    assert corpo["tamanho"] == len(PNG)
    baixado = await api.cliente.get(f"/v1/anexos/{corpo['anexo_id']}", headers=auth)
    assert baixado.status_code == 200 and baixado.content == PNG
    assert baixado.headers["content-type"] == "image/png"
    assert baixado.headers["x-content-type-options"] == "nosniff"
    assert (
        await api.cliente.get(f"/v1/anexos/{corpo['anexo_id']}", headers=outro)
    ).status_code == 404
    texto = await api.cliente.post(
        "/v1/anexos", files={"arquivo": ("nota.md", "olá".encode(), "text/plain")}, headers=auth
    )
    anexo = await api.cliente.get(f"/v1/anexos/{texto.json()['anexo_id']}", headers=auth)
    assert anexo.headers["content-disposition"].startswith("attachment")

    recusas = [
        ("x.exe", b"MZ", 415),
        ("falso.png", b"<html>", 415),
        (".oculto.png", PNG, 422),
        ("vazio.txt", b"", 422),
        ("grande.txt", b"a" * (20 * 1024 * 1024 + 1), 413),
    ]
    for nome, dados, esperado in recusas:
        r = await api.cliente.post(
            "/v1/anexos", files={"arquivo": (nome, dados, "x/y")}, headers=auth
        )
        assert r.status_code == esperado, nome
    no_limite = await api.cliente.post(
        "/v1/anexos",
        files={"arquivo": ("limite.txt", b"a" * (20 * 1024 * 1024), "text/plain")},
        headers=auth,
    )
    assert no_limite.status_code == 201


async def test_uso_agrega_por_dia_papel_e_provedor_do_proprio_usuario(api: Ambiente) -> None:
    auth, uid = await _entrar(api, "ana@exemplo.com")
    outro, oid = await _entrar(api, "bia@exemplo.com")
    hoje = datetime.now(UTC).replace(hour=12, minute=0)
    async with api.fabrica() as sessao:
        provedor = Provedor(usuario_id=uid, tipo="openai")
        sessao.add(provedor)
        await sessao.flush()

        def chamada(usuario, papel, quando, prov=None, ent=10, sai=5, custo="0.5"):
            return ChamadaModelo(
                id=uuid4(), usuario_id=usuario, provedor_id=prov, papel=papel, modelo="m",
                nivel="N2", tokens_entrada=ent, tokens_saida=sai, custo_usd=custo,
                latencia_ms=1, criado_em=quando,
            )  # fmt: skip

        sessao.add_all(
            [
                chamada(uid, "especialista", hoje, provedor.id),
                chamada(uid, "especialista", hoje, provedor.id),
                chamada(uid, "sora", hoje),
                chamada(uid, "sora", hoje - timedelta(days=40)),
                chamada(oid, "sora", hoje, custo="9"),
            ]
        )
        await sessao.commit()
    r = await api.cliente.get("/v1/uso", headers=auth)
    assert r.status_code == 200
    corpo = r.json()
    por_papel = {(i["papel"], i["provedor"]): i for i in corpo["itens"]}
    assert por_papel[("especialista", "openai")]["tokens_entrada"] == 20
    assert por_papel[("especialista", "openai")]["custo_usd"] == 1.0
    assert por_papel[("sora", None)]["tokens_saida"] == 5
    assert corpo["custo_total_usd"] == 1.5
    de = (hoje - timedelta(days=41)).date().isoformat()
    ate = (hoje - timedelta(days=39)).date().isoformat()
    antigo = await api.cliente.get("/v1/uso", params={"de": de, "ate": ate}, headers=auth)
    assert antigo.json()["custo_total_usd"] == 0.5
    assert (
        await api.cliente.get(
            "/v1/uso", params={"de": "2026-02-02", "ate": "2026-01-01"}, headers=auth
        )
    ).status_code == 422
    assert (await api.cliente.get("/v1/uso", headers=outro)).json()["custo_total_usd"] == 9.0
