# ruff: noqa: F811
"""Navegador no worker (Leme, etapa 4): Postgres e Redis reais, API em uvicorn, worker ARQ real,
Chromium real e um servidor HTTP local. ``SORA_MODELO_FALSO=1``.

O perfil do agente é o compartilhado, com login salvo (cookie) e nenhum domínio aprovado: a
primeira navegação para um domínio novo pausa a etapa e vira cartão de aprovação.
"""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.core.config import obter_configuracao
from app.modelos.enumeracoes import StatusEtapa
from app.modelos.tabelas import (
    AbaNavegador,
    Anexo,
    Aprovacao,
    Cadeia,
    EstadoNavegador,
    Etapa,
    Passo,
    Usuario,
)
from app.navegador import perfis as pf
from tests.integracao.relogio_base import Mundo, esperar, mundo  # noqa: F401
from tests.integracao.relogio_base import servicos_relogio as _servicos_testcontainers
from tests.integracao.test_fase_b_pronto import entrar, ler_sse

pytestmark = [pytest.mark.integracao, pytest.mark.filterwarnings("ignore")]

COMPARTILHADO = pf.EscolhaPerfil(tipo=pf.TipoPerfil.COMPARTILHADO)


@pytest.fixture(scope="module")
def servicos_relogio(request: pytest.FixtureRequest):
    """No Windows o loop do psycopg não cria subprocesso (o Playwright precisa); por isso estes
    testes rodam num contêiner Linux contra serviços de pé (``SORA_TESTE_PG``/``_REDIS``)."""
    import os

    if os.environ.get("SORA_TESTE_PG") and os.environ.get("SORA_TESTE_REDIS"):
        yield os.environ["SORA_TESTE_PG"], os.environ["SORA_TESTE_REDIS"]
        return
    yield from _servicos_testcontainers.__wrapped__()


class _Pagina(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        porta = self.server.server_address[1]
        corpo = (
            "<title>Painel de teste</title><h1>Olá</h1>"
            f'<button id="ok">Confirmar</button><a href="http://127.0.0.1:{porta}/x">Ir</a>'
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Set-Cookie", "sessao=login-do-usuario; Path=/; Max-Age=3600")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_a: Any) -> None:
        return


@pytest.fixture(autouse=True)
def _navegador_local(monkeypatch: pytest.MonkeyPatch):
    """Estes testes lançam o Chromium local: não herdam ``NAVEGADOR_CDP_URL`` do ``.env`` nem do
    ``tests/conftest.py``. Valem igual com a variável definida ou não."""
    monkeypatch.setenv("NAVEGADOR_CDP_URL", "")
    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()


@pytest.fixture
def servidor_local(monkeypatch: pytest.MonkeyPatch):
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Pagina)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    async def sem_guarda(_url: str) -> None:  # o alvo é loopback; a guarda tem testes próprios
        return None

    monkeypatch.setattr("app.navegador.persistente.validar_destino", sem_guarda)
    yield f"http://localhost:{servidor.server_address[1]}/"
    servidor.shutdown()


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch, servidor_local: str):

    async def compartilhado(self, agente_id, usuario_id):
        return pf.EscolhaPerfil(tipo=pf.TipoPerfil.COMPARTILHADO)

    monkeypatch.setattr(
        "app.navegador.repositorio.RepositorioNavegador.escolha_do_agente", compartilhado
    )
    yield servidor_local


async def _perfil_logado(mundo: Mundo, email: str, aprovados: tuple[str, ...] = ()) -> UUID:
    async with mundo.fabrica() as sessao:
        usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
        assert usuario_id is not None
        particao = pf.particao(usuario_id, usuario_id, COMPARTILHADO)
        estado = {
            "cookies": [
                {"name": "sessao", "value": "segredo", "domain": "banco.exemplo", "path": "/"}
            ],
            "origins": [],
        }
        for dominio in aprovados:
            estado = pf.com_dominio_aprovado(estado, dominio)
        sessao.add(
            EstadoNavegador(
                particao=particao,
                usuario_id=usuario_id,
                estado_cifrado=pf.cifrar_estado(estado, usuario_id=usuario_id, particao_=particao),
            )
        )
        await sessao.commit()
    return usuario_id


async def _cartao(mundo: Mundo, usuario_id: UUID) -> Aprovacao:
    async def achar() -> Aprovacao | None:
        async with mundo.fabrica() as sessao:
            return await sessao.scalar(
                select(Aprovacao).where(
                    Aprovacao.usuario_id == usuario_id,
                    Aprovacao.acao["tipo"].astext == "aprovar_dominio",
                )
            )

    try:
        return await esperar(achar, 60)
    except TimeoutError:
        async with mundo.fabrica() as sessao:
            etapas = [(e.status, e.erro) for e in await sessao.scalars(select(Etapa))]
            passos = [
                (p.ferramenta, str(p.resultado)[:200])
                for p in await sessao.scalars(select(Passo))
                if p.ferramenta
            ]
        raise AssertionError(f"sem cartão; etapas={etapas}; passos={passos}") from None


def _concluiu(nome: str, dados: dict) -> bool:
    return nome == "cadeia.atualizada" and dados.get("status") in ("concluida", "falhou")


async def test_dominio_novo_em_perfil_logado_pausa_aprova_e_navega(mundo: Mundo, site: str) -> None:
    email = "leme-a@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        usuario_id = await _perfil_logado(mundo, email)
        await mundo.iniciar_worker()
        r = await cliente.post(
            "/v1/conversas",
            headers=auth,
            json={"texto": f"pesquise a página [navegador:{site}]", "anexos": []},
        )
        assert r.status_code == 201, r.text
        conversa_id = r.json()["id"]
        leitura = asyncio.create_task(ler_sse(cliente, conversa_id, auth, ate=_concluiu))

        cartao = await _cartao(mundo, usuario_id)
        assert cartao.acao["dominio"] == "localhost"

        async def pausada() -> bool:
            async with mundo.fabrica() as sessao:
                etapa = await sessao.get(Etapa, cartao.etapa_id)
                return etapa.status == StatusEtapa.AGUARDANDO_APROVACAO

        assert await esperar(pausada, 30)
        assert not leitura.done()

        decidida = await cliente.post(
            f"/v1/aprovacoes/{cartao.id}/decidir", headers=auth, json={"decisao": "sempre_permitir"}
        )
        assert decidida.status_code == 204, decidida.text
        eventos = await asyncio.wait_for(leitura, 120)

    pedida = next(d for n, d in eventos if n == "aprovacao.pedida")
    assert pedida["tipo"] == "aprovar_dominio" and pedida["dominio"] == "localhost"
    assert [o["valor"] for o in pedida["opcoes"]] == ["sempre_permitir", "negar"]
    assert pedida["agente_id"] and pedida["perfil"] == {"tipo": "compartilhado"}
    assert "segredo" not in str(eventos)

    passos = [
        d
        for n, d in eventos
        if n == "passo" and str(d.get("ferramenta", "")).startswith("navegador")
    ]
    ferramentas = {p["ferramenta"] for p in passos}
    assert {"navegador_abrir", "navegador_observar", "navegador_capturar"} <= ferramentas
    observar = next(
        p for p in passos if p["ferramenta"] == "navegador_observar" and p.get("resultado")
    )
    assert "Painel de teste" in str(observar["resultado"]) and observar["resultado"]["rastro"]
    captura = next(
        p for p in passos if p["ferramenta"] == "navegador_capturar" and p.get("resultado")
    )["resultado"]
    assert captura.get("tipo") == "image/png", captura
    assert captura["tamanho"] > 1000
    assert 0 or (captura["tipo"] == "image/png" and captura["tamanho"] > 1000)
    abas = [d for n, d in eventos if n == "navegador.aba"]
    assert abas and abas[-1]["url"].startswith(site) and abas[-1]["carregada"] is True
    # ao retomar não nasce um segundo cartão
    assert [n for n, _ in eventos].count("aprovacao.pedida") == 1

    async with mundo.fabrica() as sessao:
        cadeia = await sessao.scalar(select(Cadeia).where(Cadeia.conversa_id == UUID(conversa_id)))
        assert cadeia is not None and cadeia.status.value == "concluida"
        estado_cifrado = await sessao.scalar(
            select(EstadoNavegador.estado_cifrado).where(EstadoNavegador.usuario_id == usuario_id)
        )
        estado = pf.decifrar_estado(
            estado_cifrado,
            usuario_id=usuario_id,
            particao_=pf.particao(usuario_id, usuario_id, COMPARTILHADO),
        )
        assert "localhost" in pf.dominios_aprovados(estado)
        assert estado["cookies"], "o login salvo continua no perfil"
        anexo = await sessao.get(Anexo, UUID(captura["anexo_id"]))
        assert anexo is not None and anexo.origem == "navegador"
        assert (await sessao.scalars(select(AbaNavegador))).all()


async def test_negar_domino_nao_navega_e_nao_aprova(mundo: Mundo, site: str) -> None:
    email = "leme-b@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        usuario_id = await _perfil_logado(mundo, email)
        await mundo.iniciar_worker()
        r = await cliente.post(
            "/v1/conversas",
            headers=auth,
            json={"texto": f"pesquise a página [navegador:{site}]", "anexos": []},
        )
        conversa_id = r.json()["id"]
        leitura = asyncio.create_task(ler_sse(cliente, conversa_id, auth, ate=_concluiu))
        cartao = await _cartao(mundo, usuario_id)
        negada = await cliente.post(
            f"/v1/aprovacoes/{cartao.id}/decidir", headers=auth, json={"decisao": "negar"}
        )
        assert negada.status_code == 204, negada.text
        eventos = await asyncio.wait_for(leitura, 120)
    ferramentas = {d["ferramenta"] for n, d in eventos if n == "passo" and d.get("ferramenta")}
    assert "navegador_observar" not in ferramentas
    async with mundo.fabrica() as sessao:
        estado_cifrado = await sessao.scalar(
            select(EstadoNavegador.estado_cifrado).where(EstadoNavegador.usuario_id == usuario_id)
        )
        estado = pf.decifrar_estado(
            estado_cifrado,
            usuario_id=usuario_id,
            particao_=pf.particao(usuario_id, usuario_id, COMPARTILHADO),
        )
        assert pf.dominios_aprovados(estado) == set()


async def _cartao_novo(mundo: Mundo, usuario_id: UUID, dominio: str) -> Aprovacao:
    async def achar() -> Aprovacao | None:
        async with mundo.fabrica() as sessao:
            return await sessao.scalar(
                select(Aprovacao).where(
                    Aprovacao.usuario_id == usuario_id,
                    Aprovacao.acao["tipo"].astext == "aprovar_dominio",
                    Aprovacao.acao["dominio"].astext == dominio,
                )
            )

    try:
        return await esperar(achar, 60)
    except TimeoutError:
        async with mundo.fabrica() as sessao:
            etapas = [(e.status, e.erro) for e in await sessao.scalars(select(Etapa))]
            passos = [
                (p.ferramenta, str(p.resultado)[:300])
                for p in await sessao.scalars(select(Passo))
                if p.ferramenta
            ]
        cartoes = [dict(c.acao) for c in await _todos_os_cartoes(mundo, usuario_id)]
        raise AssertionError(
            f"sem cartão de {dominio}; etapas={etapas}; passos={passos}; cartoes={cartoes}"
        ) from None


async def test_clique_em_dominio_barrado_vira_cartao_e_aba_sobrevive_ao_reinicio(
    mundo: Mundo, site: str
) -> None:
    email = "leme-c@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        usuario_id = await _perfil_logado(mundo, email)
        await mundo.iniciar_worker()
        r = await cliente.post(
            "/v1/conversas",
            headers=auth,
            json={"texto": f"pesquise [navegador:{site}] [navegador-clicar:Ir]", "anexos": []},
        )
        conversa_id = r.json()["id"]
        leitura = asyncio.create_task(ler_sse(cliente, conversa_id, auth, ate=_concluiu))
        aprovador = asyncio.create_task(_aprovar_tudo(cliente, mundo, auth, usuario_id, leitura))
        eventos = await asyncio.wait_for(leitura, 120)
        await aprovador

        pedidas = [d for n, d in eventos if n == "aprovacao.pedida" and d.get("tipo")]
        assert [p["dominio"] for p in pedidas] == ["localhost", "127.0.0.1"]
        assert pedidas[1]["url"].startswith("http://127.0.0.1:")
        abas = [d for n, d in eventos if n == "navegador.aba"]
        assert abas[-1]["url"].endswith("/x"), abas[-1]
        acao = [
            d
            for n, d in eventos
            if n == "passo" and d.get("ferramenta") == "navegador_acao" and d.get("resultado")
        ]
        assert acao and acao[-1]["resultado"]["rastro"]["comando"]

        # ---- assumir e devolver (o agente não mexe enquanto o usuário está na aba)
        lista = (await cliente.get("/v1/navegador/abas", headers=auth)).json()
        assert len(lista) == 1
        aba_id = lista[0]["aba_id"]
        assumida = await cliente.post(f"/v1/navegador/abas/{aba_id}/assumir", headers=auth)
        assert assumida.json()["assumida_pelo_usuario"] is True
        devolvida = await cliente.post(f"/v1/navegador/abas/{aba_id}/devolver", headers=auth)
        assert devolvida.json()["assumida_pelo_usuario"] is False

        # ---- reinicia o worker: a aba volta descarregada, no mesmo perfil
        await mundo.parar_worker()
        await mundo.iniciar_worker()

        async def restaurada() -> Any:
            amb = (mundo._worker.ctx or {}).get("navegador")
            return amb is not None and [a for a in amb.gerente.para_salvar() if str(a.id) == aba_id]

        (aba,) = await esperar(restaurada, 60)
        assert aba.carregada is False and aba.url.endswith("/x")
        assert aba.particao == pf.particao(usuario_id, usuario_id, COMPARTILHADO)


async def test_rotina_sem_supervisao_usa_aba_efemera_sem_login(mundo: Mundo, site: str) -> None:
    from uuid import uuid4

    from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
    from app.navegador import NavegadorAbrir
    from app.navegador.abas import NavegadorFecharAba
    from app.navegador.arvore.ferramentas import NavegadorObservar

    email = "leme-d@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        await entrar(cliente, mundo.fabrica, email)
    usuario_id = await _perfil_logado(mundo, email)
    await mundo.iniciar_worker()

    async def pronto() -> Any:
        return (mundo._worker.ctx or {}).get("navegador")

    amb = await esperar(pronto, 60)
    agente_id = uuid4()
    sem = ContextoFerramenta(
        usuario_id=usuario_id, agente_id=agente_id, conversa_id=uuid4(), sem_supervisao=True
    )
    efemera = await amb.executar("navegador_abrir", NavegadorAbrir(url=site), sem)
    # perfil efêmero: sem cookies de login, sem revisão de domínio e nada gravado no banco
    (aba,) = amb.gerente.do_agente(agente_id, so_efemeras=True)
    assert aba.perfil_efemero and str(aba.id) == efemera["aba_id"]
    cookies = await amb.motor.pagina(aba).context.cookies()
    assert all(c["value"] != "segredo" for c in cookies)  # nada do login salvo
    async with mundo.fabrica() as sessao:
        assert (await sessao.get(AbaNavegador, aba.id)) is None
    visto = await amb.executar("navegador_observar", NavegadorObservar(aba_id=aba.id), sem)
    assert "Painel de teste" in visto["resumo"]
    # a rotina não alcança uma aba com perfil salvo (nem abre uma logada por engano)
    aba_logada = await amb.gerente.abrir(
        usuario_id=usuario_id,
        agente_id=agente_id,
        escolha=COMPARTILHADO,
        url=None,
    )
    with pytest.raises(ErroFerramenta):
        await amb.executar("navegador_fechar_aba", NavegadorFecharAba(aba_id=aba_logada.id), sem)
    await amb.executar("navegador_fechar_aba", NavegadorFecharAba(aba_id=aba.id), sem)
    assert amb.gerente.do_agente(agente_id, so_efemeras=True) == []
    await amb.gerente.fechar(aba_logada.id, agente_id)


async def _usuario_id(mundo: Mundo, email: str) -> UUID:
    async with mundo.fabrica() as sessao:
        return await sessao.scalar(select(Usuario.id).where(Usuario.email == email))


async def test_abrir_aba_no_perfil_novo_para_o_usuario_logar(
    mundo: Mundo, servidor_local: str
) -> None:
    email = "leme-e@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=90) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        usuario_id = await _usuario_id(mundo, email)
        await mundo.iniciar_worker()
        perfil = (
            await cliente.post("/v1/navegador/perfis", headers=auth, json={"nome": "Meu banco"})
        ).json()
        aberta = await cliente.post(
            f"/v1/navegador/perfis/{perfil['perfil_id']}/abrir",
            headers=auth,
            json={"url": servidor_local},
        )
        assert aberta.status_code == 202, aberta.text
        estado = aberta.json()
        assert estado["assumida_pelo_usuario"] is True and estado["carregada"] is True
        assert estado["url"].startswith(servidor_local) and estado["titulo"] == "Painel de teste"
        abas = (await cliente.get("/v1/navegador/abas", headers=auth)).json()
        assert [x["aba_id"] for x in abas] == [estado["aba_id"]]
        assert abas[0]["assumida_pelo_usuario"] is True

        # o login feito na aba (cookie) chega ao banco sem nenhum agente rodando
        particao = pf.particao(
            usuario_id,
            UUID(estado["agente_id"]),
            pf.EscolhaPerfil(tipo=pf.TipoPerfil.NOMEADO, perfil_id=UUID(perfil["perfil_id"])),
        )

        async def salvo() -> bool:
            async with mundo.fabrica() as sessao:
                linha = await sessao.get(EstadoNavegador, particao)
                if linha is None:
                    return False
                dados = pf.decifrar_estado(
                    linha.estado_cifrado, usuario_id=usuario_id, particao_=particao
                )
                tem_cookie = any(c["name"] == "sessao" for c in dados["cookies"])
                return tem_cookie and "localhost" in pf.dominios_aprovados(dados)

        await esperar(salvo, 60)
        lista = (await cliente.get("/v1/navegador/perfis", headers=auth)).json()
        assert lista[0]["dominios_aprovados"] == ["localhost"]
        assert "login-do-usuario" not in str(lista)
        devolvida = await cliente.post(
            f"/v1/navegador/abas/{estado['aba_id']}/devolver", headers=auth
        )
        assert devolvida.json()["assumida_pelo_usuario"] is False


async def test_agente_efemero_abre_aba_descartavel_sem_login(
    mundo: Mundo, servidor_local: str
) -> None:
    from uuid import uuid4

    from app.ferramentas.base import ContextoFerramenta
    from app.modelos.enumeracoes import TipoAgente
    from app.modelos.tabelas import Agente
    from app.navegador import NavegadorAbrir

    email = "leme-f@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        usuario_id = await _usuario_id(mundo, email)
        async with mundo.fabrica() as sessao:
            sora = await sessao.scalar(
                select(Agente.id).where(
                    Agente.usuario_id == usuario_id, Agente.tipo == TipoAgente.SORA
                )
            )
        # o perfil compartilhado tem login salvo; o agente efêmero não o enxerga
        particao = pf.particao(usuario_id, sora, COMPARTILHADO)
        estado = {
            "cookies": [{"name": "s", "value": "x", "domain": "localhost", "path": "/"}],
            "origins": [],
        }
        async with mundo.fabrica() as sessao:
            sessao.add(
                EstadoNavegador(
                    particao=particao,
                    usuario_id=usuario_id,
                    estado_cifrado=pf.cifrar_estado(
                        estado, usuario_id=usuario_id, particao_=particao
                    ),
                )
            )
            await sessao.commit()
        escolha = await cliente.put(
            f"/v1/agentes/{sora}/navegador", headers=auth, json={"tipo": "efemero"}
        )
        assert escolha.status_code == 200
        await mundo.iniciar_worker()

        async def pronto() -> Any:
            return (mundo._worker.ctx or {}).get("navegador")

        amb = await esperar(pronto, 60)
        ctx = ContextoFerramenta(usuario_id=usuario_id, agente_id=sora, conversa_id=uuid4())
        aberta = await amb.executar("navegador_abrir", NavegadorAbrir(url=servidor_local), ctx)
        (aba,) = amb.gerente.do_agente(sora)
        assert aba.perfil_efemero and str(aba.id) == aberta["aba_id"]
        cookies = await amb.motor.pagina(aba).context.cookies()
        assert all(c["name"] != "s" for c in cookies)  # nada do login do compartilhado
        async with mundo.fabrica() as sessao:
            assert await sessao.get(AbaNavegador, aba.id) is None  # nem fica salva
            pedidos = select(Aprovacao).where(Aprovacao.usuario_id == usuario_id)
            assert not (await sessao.scalars(pedidos)).all()  # sem cartão


async def _todos_os_cartoes(mundo: Mundo, usuario_id: UUID) -> list[Aprovacao]:
    async with mundo.fabrica() as sessao:
        return list(
            (
                await sessao.scalars(select(Aprovacao).where(Aprovacao.usuario_id == usuario_id))
            ).all()
        )


async def _aprovar_tudo(cliente, mundo: Mundo, auth: dict, usuario_id: UUID, leitura) -> None:
    """O usuário aprova o que aparecer: o revisor do clique (uma vez) e o domínio (sempre)."""
    decididas: set[UUID] = set()
    while not leitura.done():
        for cartao in await _todos_os_cartoes(mundo, usuario_id):
            if cartao.id in decididas or cartao.status.value != "pendente":
                continue
            domino = cartao.acao.get("tipo") == "aprovar_dominio"
            resposta = await cliente.post(
                f"/v1/aprovacoes/{cartao.id}/decidir",
                headers=auth,
                json={"decisao": "sempre_permitir" if domino else "permitir_uma_vez"},
            )
            assert resposta.status_code == 204, resposta.text
            decididas.add(cartao.id)
        await asyncio.sleep(0.3)


async def _segundo_worker(mundo: Mundo) -> Any:
    from arq.connections import RedisSettings
    from arq.worker import create_worker

    from workers.configuracao import WorkerSettings

    worker = create_worker(
        WorkerSettings,
        redis_settings=RedisSettings.from_dsn(mundo.url_redis),
        handle_signals=False,
        poll_delay=0.1,
    )
    tarefa = asyncio.create_task(worker.async_run())

    async def pronto() -> Any:
        return (worker.ctx or {}).get("navegador")

    await esperar(pronto, 60)
    return worker, tarefa


async def test_dois_workers_enxergam_as_mesmas_abas(mundo: Mundo, site: str) -> None:
    """E4-M3: a aba aberta no worker A é usada, fechada e vista como fechada no worker B."""
    from uuid import uuid4

    from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
    from app.navegador import NavegadorAbrir
    from app.navegador.abas import NavegadorFecharAba
    from app.navegador.arvore.ferramentas import NavegadorObservar
    from tests.integracao.test_fase_b_pronto import _fechar_worker

    email = "leme-g@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        await entrar(cliente, mundo.fabrica, email)
    usuario_id = await _usuario_id(mundo, email)
    await _perfil_logado(mundo, email, aprovados=("localhost",))
    await mundo.iniciar_worker()
    segundo, tarefa_b = await _segundo_worker(mundo)
    try:

        async def pronto() -> Any:
            return (mundo._worker.ctx or {}).get("navegador")

        a = await esperar(pronto, 60)
        b = segundo.ctx["navegador"]
        assert a is not b
        agente = uuid4()
        async with mundo.fabrica() as sessao:  # o agente precisa existir (chave estrangeira)
            from app.modelos.enumeracoes import TipoAgente
            from app.modelos.tabelas import Agente

            sessao.add(
                Agente(
                    id=agente,
                    usuario_id=usuario_id,
                    nome="Atlas",
                    papel="Pesquisa",
                    cor="#56A8FF",
                    tipo=TipoAgente.INDIVIDUAL,
                )
            )
            await sessao.commit()
        ctx = ContextoFerramenta(usuario_id=usuario_id, agente_id=agente, conversa_id=uuid4())

        aberta = await a.executar("navegador_abrir", NavegadorAbrir(url=site), ctx)
        aba_id = UUID(aberta["aba_id"])
        assert aba_id not in b.gerente._abas  # só o A conhece a aba (memória)

        # o B recria a aba pelo estado salvo e consegue observar a página
        visto = await b.executar("navegador_observar", NavegadorObservar(aba_id=aba_id), ctx)
        assert "Painel de teste" in visto["resumo"]
        listadas = await b.executar("navegador_abas", type("A", (), {})(), ctx)
        assert [x["aba_id"] for x in listadas["abas"]] == [str(aba_id)]

        # o B fecha; o A, na próxima chamada, percebe e responde com erro claro (sem usar aba velha)
        await b.executar("navegador_fechar_aba", NavegadorFecharAba(aba_id=aba_id), ctx)
        with pytest.raises(ErroFerramenta, match="não existe mais"):
            await a.executar("navegador_observar", NavegadorObservar(aba_id=aba_id), ctx)
        assert aba_id not in a.gerente._abas

        # aba temporária (rotina) vive só no worker que a abriu: o outro responde com erro claro
        sem = ContextoFerramenta(
            usuario_id=usuario_id, agente_id=agente, conversa_id=uuid4(), sem_supervisao=True
        )
        efemera = await a.executar("navegador_abrir", NavegadorAbrir(url=site), sem)
        with pytest.raises(ErroFerramenta, match="outro servidor"):
            await b.executar(
                "navegador_observar", NavegadorObservar(aba_id=UUID(efemera["aba_id"])), sem
            )
        await a.executar(
            "navegador_fechar_aba", NavegadorFecharAba(aba_id=UUID(efemera["aba_id"])), sem
        )
    finally:
        await _fechar_worker(segundo)
        tarefa_b.cancel()


async def test_cartao_de_dominio_novo_quando_expira_ou_o_dominio_e_revogado(
    mundo: Mundo, site: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E4-B2 e E4-B1: cartão repetido nunca pausa sem cartão; o perfil vai ao app sem partição."""
    from uuid import uuid4

    from app.ferramentas.base import ContextoFerramenta
    from app.modelos.enumeracoes import StatusAprovacao
    from app.navegador.abas import RevisaoNavegacaoNecessaria
    from app.navegador.repositorio import aprovar_dominio_no_perfil

    email = "leme-h@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        await entrar(cliente, mundo.fabrica, email)
    usuario_id = await _usuario_id(mundo, email)
    await _perfil_logado(mundo, email)
    await mundo.iniciar_worker()

    async def pronto() -> Any:
        return (mundo._worker.ctx or {}).get("navegador")

    amb = await esperar(pronto, 60)
    particao = pf.particao(usuario_id, usuario_id, COMPARTILHADO)
    publicados: list[Any] = []

    async def captura(redis, evento, conversa_id, usuario):
        publicados.append(evento)

    monkeypatch.setattr("app.ferramentas.navegador_worker.publicar_evento", captura)
    monkeypatch.setattr("langgraph.types.interrupt", lambda _valor: "sempre_permitir")
    agente = await _novo_agente(mundo, usuario_id)
    ctx = ContextoFerramenta(
        usuario_id=usuario_id, agente_id=agente, conversa_id=uuid4(), etapa_id=None
    )
    revisao = RevisaoNavegacaoNecessaria("localhost", aba_id=uuid4(), url=site, particao=particao)

    async def cartoes() -> list[Aprovacao]:
        todos = await _todos_os_cartoes(mundo, usuario_id)
        return sorted(todos, key=lambda c: str(c.id))

    async def marcar(cartao: Aprovacao, status: StatusAprovacao) -> None:
        async with mundo.fabrica() as sessao:
            linha = await sessao.get(Aprovacao, cartao.id)
            linha.status = status
            await sessao.commit()

    async def aprovar_no_perfil() -> None:
        async with mundo.fabrica() as sessao:
            await aprovar_dominio_no_perfil(
                sessao, particao=particao, usuario_id=usuario_id, dominio="localhost"
            )
            await sessao.commit()

    # 1) primeiro pedido: um cartão pendente, com o perfil no formato do app
    await amb._pedir_revisao(ctx, "navegador_abrir", revisao)
    (primeiro,) = await cartoes()
    assert len(publicados) == 1
    assert publicados[0].perfil == {"tipo": "compartilhado"}
    assert "particao" not in str(publicados[0].perfil)

    # 2) o usuário aprova e a ferramenta roda de novo (retomada): o mesmo cartão, nenhum novo
    await marcar(primeiro, StatusAprovacao.PERMITIDA)
    await aprovar_no_perfil()
    resposta = await amb._pedir_revisao(ctx, "navegador_abrir", revisao)
    assert resposta.startswith("Domínio aprovado")
    assert len(await cartoes()) == 1 and len(publicados) == 1

    # 3) o usuário revoga o domínio e a mesma etapa navega de novo: nasce um cartão novo
    async with mundo.fabrica() as sessao:
        estado = await sessao.get(EstadoNavegador, particao)
        dados = pf.decifrar_estado(estado.estado_cifrado, usuario_id=usuario_id, particao_=particao)
        estado.estado_cifrado = pf.cifrar_estado(
            pf.sem_dominio_aprovado(dados, "localhost"), usuario_id=usuario_id, particao_=particao
        )
        await sessao.commit()
    await amb._pedir_revisao(ctx, "navegador_abrir", revisao)
    assert len(await cartoes()) == 2 and len(publicados) == 2

    # 4) cartão que expirou sem resposta também é substituído
    pendentes = [c for c in await cartoes() if c.status == StatusAprovacao.PENDENTE]
    assert len(pendentes) == 1
    await marcar(pendentes[0], StatusAprovacao.EXPIRADA)
    await amb._pedir_revisao(ctx, "navegador_abrir", revisao)
    assert len(await cartoes()) == 3 and len(publicados) == 3
    assert [c.status for c in await cartoes()].count(StatusAprovacao.PENDENTE) == 1


async def test_abrir_aba_no_perfil_devolve_erro_em_portugues(
    mundo: Mundo, servidor_local: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = "leme-i@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=90) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        await mundo.iniciar_worker()
        perfil = (
            await cliente.post("/v1/navegador/perfis", headers=auth, json={"nome": "Erro"})
        ).json()
        monkeypatch.setattr(
            "app.navegador.abas.GerenteAbas.abrir",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("falha interna: senha=segredo")),
        )
        quebrada = await cliente.post(
            f"/v1/navegador/perfis/{perfil['perfil_id']}/abrir",
            headers=auth,
            json={"url": servidor_local},
        )
        assert quebrada.status_code == 409
        assert quebrada.json()["detail"] == (
            "Não consegui abrir a aba agora. Tente de novo em instantes."
        )
        assert "segredo" not in quebrada.text and "RuntimeError" not in quebrada.text


async def _novo_agente(mundo: Mundo, usuario_id: UUID) -> UUID:
    from uuid import uuid4

    from app.modelos.enumeracoes import TipoAgente
    from app.modelos.tabelas import Agente

    agente = uuid4()
    async with mundo.fabrica() as sessao:
        sessao.add(
            Agente(
                id=agente,
                usuario_id=usuario_id,
                nome="Atlas",
                papel="Pesquisa",
                cor="#56A8FF",
                tipo=TipoAgente.INDIVIDUAL,
            )
        )
        await sessao.commit()
    return agente


async def test_fechar_aba_pela_api_libera_a_vaga_no_worker(
    mundo: Mundo, servidor_local: str
) -> None:
    """Abre e fecha 10 vezes pela API: o limite de 8 abas por agente não pode ser alcançado."""
    from app.navegador.abas import MAX_ABAS_POR_AGENTE

    email = "leme-j@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=90) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        await mundo.iniciar_worker()
        perfil = (
            await cliente.post("/v1/navegador/perfis", headers=auth, json={"nome": "Vazamento"})
        ).json()
        for volta in range(MAX_ABAS_POR_AGENTE + 2):
            aberta = await cliente.post(
                f"/v1/navegador/perfis/{perfil['perfil_id']}/abrir",
                headers=auth,
                json={"url": servidor_local},
            )
            assert aberta.status_code == 202, (volta, aberta.text)
            apagada = await cliente.delete(
                f"/v1/navegador/abas/{aberta.json()['aba_id']}", headers=auth
            )
            assert apagada.status_code == 204
        assert (await cliente.get("/v1/navegador/abas", headers=auth)).json() == []


async def test_destino_interno_e_recusado_sem_cartao_de_dominio(
    mundo: Mundo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E4F2-B3: SSRF antes da revisão. Endereço privado: erro em português, nenhum cartão e
    nenhum domínio aprovado, nem pela navegação do agente nem por /abrir."""
    from uuid import uuid4

    from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
    from app.navegador import NavegadorAbrir

    async def compartilhado(self, agente_id, usuario_id):
        return pf.EscolhaPerfil(tipo=pf.TipoPerfil.COMPARTILHADO)

    monkeypatch.setattr(
        "app.navegador.repositorio.RepositorioNavegador.escolha_do_agente", compartilhado
    )
    email = "leme-k@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        usuario_id = await _perfil_logado(mundo, email)
        await mundo.iniciar_worker()

        async def pronto() -> Any:
            return (mundo._worker.ctx or {}).get("navegador")

        amb = await esperar(pronto, 60)
        agente = await _novo_agente(mundo, usuario_id)
        ctx = ContextoFerramenta(usuario_id=usuario_id, agente_id=agente, conversa_id=uuid4())
        for alvo in ("http://127.0.0.1:9/", "http://10.0.0.5/painel", "http://localhost:9/"):
            with pytest.raises(ErroFerramenta, match="Endereço recusado"):
                await amb.executar("navegador_abrir", NavegadorAbrir(url=alvo), ctx)
        assert await _todos_os_cartoes(mundo, usuario_id) == []

        perfil = (
            await cliente.post("/v1/navegador/perfis", headers=auth, json={"nome": "Interno"})
        ).json()
        recusada = await cliente.post(
            f"/v1/navegador/perfis/{perfil['perfil_id']}/abrir",
            headers=auth,
            json={"url": "http://10.0.0.5/painel"},
        )
        assert recusada.status_code == 409
        assert "Endereço recusado" in recusada.json()["detail"]
        lista = (await cliente.get("/v1/navegador/perfis", headers=auth)).json()
        assert all(p["dominios_aprovados"] == [] for p in lista)
        assert await _todos_os_cartoes(mundo, usuario_id) == []
