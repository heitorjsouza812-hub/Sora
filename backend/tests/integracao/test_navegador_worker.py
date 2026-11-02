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
    testes podem rodar num contêiner Linux contra serviços já de pé (``SORA_TESTE_PG``/``_REDIS``)."""
    import os

    if os.environ.get("SORA_TESTE_PG") and os.environ.get("SORA_TESTE_REDIS"):
        yield os.environ["SORA_TESTE_PG"], os.environ["SORA_TESTE_REDIS"]
        return
    yield from _servicos_testcontainers.__wrapped__()


PAGINA = (
    "<title>Painel de teste</title><h1>Olá</h1>"
    '<button id="ok">Confirmar</button><a href="/x">Ir</a>'
).encode()


class _Pagina(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGINA)))
        self.end_headers()
        self.wfile.write(PAGINA)

    def log_message(self, *_a: Any) -> None:
        return


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch):
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Pagina)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    async def sem_guarda(_url: str) -> None:  # o alvo é loopback; a guarda tem testes próprios
        return None

    monkeypatch.setattr("app.navegador.persistente.validar_destino", sem_guarda)

    async def compartilhado(self, agente_id, usuario_id):
        return pf.EscolhaPerfil(tipo=pf.TipoPerfil.COMPARTILHADO)

    monkeypatch.setattr(
        "app.navegador.repositorio.RepositorioNavegador.escolha_do_agente", compartilhado
    )
    yield f"http://localhost:{servidor.server_address[1]}/"
    servidor.shutdown()


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
        async with mundo.fabrica() as sessao:
            etapa = await sessao.get(Etapa, cartao.etapa_id)
            assert etapa.status == StatusEtapa.AGUARDANDO_APROVACAO
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
    assert 0 or captura["tipo"] == "image/png" and captura["tamanho"] > 1000
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
