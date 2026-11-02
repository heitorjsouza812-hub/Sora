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


async def _perfil_logado(mundo: Mundo, email: str) -> UUID:
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
    assert pedida["agente_id"] and "particao" in pedida["perfil"]
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
        raise AssertionError(f"sem cartão de {dominio}; etapas={etapas}; passos={passos}") from None


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
        for dominio in ("localhost", "127.0.0.1"):
            cartao = await _cartao_novo(mundo, usuario_id, dominio)
            ok = await cliente.post(
                f"/v1/aprovacoes/{cartao.id}/decidir",
                headers=auth,
                json={"decisao": "sempre_permitir"},
            )
            assert ok.status_code == 204, ok.text
        eventos = await asyncio.wait_for(leitura, 120)

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
