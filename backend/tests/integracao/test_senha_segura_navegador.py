# ruff: noqa: F811
"""Senha segura no navegador do bot, com Chromium, Postgres e Redis de verdade.

O bot aponta o campo de senha, o cartão aparece, o usuário manda a senha pela API (fica cifrada
no Redis), o turno retoma e o campo é preenchido na página. O modelo nunca recebe o valor.
A pausa e a retomada do LangGraph (``interrupt``) são simuladas; o resto é o caminho real.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select

from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.modelos.enumeracoes import StatusAprovacao
from app.modelos.tabelas import Aprovacao
from app.navegador import NavegadorAbrir
from app.navegador import perfis as pf
from app.navegador.abas import NavegadorPedirSenha
from app.navegador.senha_segura import CHAVE_REDIS
from tests.integracao.relogio_base import Mundo, esperar, mundo  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar
from tests.integracao.test_navegador_worker import (  # noqa: F401
    _navegador_local,
    _novo_agente,
    _usuario_id,
    servicos_relogio,
)

pytestmark = pytest.mark.integracao

SENHA = "S3nha-Do-Usuario!"


class _Login(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        corpo = (
            "<title>Entrar</title><form>"
            '<label>Usuário <input id="u" name="usuario"></label>'
            '<label>Senha <input id="s" name="senha" type="password"></label>'
            "<button type='button'>Entrar</button></form>"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_a: Any) -> None:
        return


@pytest.fixture
def pagina_de_login(monkeypatch: pytest.MonkeyPatch):
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Login)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    async def sem_guarda(_url: str) -> None:  # o alvo é loopback; a guarda tem testes próprios
        return None

    async def compartilhado(self, agente_id, usuario_id):
        return pf.EscolhaPerfil(tipo=pf.TipoPerfil.COMPARTILHADO)

    monkeypatch.setattr("app.navegador.persistente.validar_destino", sem_guarda)
    monkeypatch.setattr(
        "app.navegador.repositorio.RepositorioNavegador.escolha_do_agente", compartilhado
    )
    yield f"http://localhost:{servidor.server_address[1]}/"
    servidor.shutdown()


class _Pausa(Exception):
    """No LangGraph de verdade, ``interrupt`` pausa o turno aqui."""


async def test_senha_vai_direto_para_o_campo_sem_passar_pelo_modelo(
    mundo: Mundo, pagina_de_login: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = "senha-segura@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        usuario_id = await _usuario_id(mundo, email)
        await mundo.iniciar_worker()

        async def pronto() -> Any:
            return (mundo._worker.ctx or {}).get("navegador")

        amb = await esperar(pronto, 60)
        agente = await _novo_agente(mundo, usuario_id)
        ctx = ContextoFerramenta(usuario_id=usuario_id, agente_id=agente, conversa_id=uuid4())
        aberta = await amb.executar("navegador_abrir", NavegadorAbrir(url=pagina_de_login), ctx)
        aba_id = UUID(aberta["aba_id"])
        navegador = await amb.arvore.navegador_da_aba(ctx, aba_id)
        campo_senha = (await navegador.procurar(nome="Senha", primeiro=True)).dados[
            "correspondencias"
        ][0]["ref"]
        campo_usuario = (await navegador.procurar(nome="Usuário", primeiro=True)).dados[
            "correspondencias"
        ][0]["ref"]

        # campo que não é de senha e rotina (ninguém olhando) são recusados
        with pytest.raises(ErroFerramenta, match="não é de senha"):
            await amb.executar(
                "navegador_pedir_senha",
                NavegadorPedirSenha(ref=campo_usuario, motivo="entrar", aba_id=aba_id),
                ctx,
            )

        # 1) pede a senha: o cartão aparece e o turno pausa
        def pausar(_valor: Any) -> Any:
            raise _Pausa

        monkeypatch.setattr("langgraph.types.interrupt", pausar)
        pedido = NavegadorPedirSenha(ref=campo_senha, motivo="entrar no painel", aba_id=aba_id)
        with pytest.raises(_Pausa):
            await amb.executar("navegador_pedir_senha", pedido, ctx)
        async with mundo.fabrica() as sessao:
            (cartao,) = (
                await sessao.scalars(
                    select(Aprovacao).where(
                        Aprovacao.usuario_id == usuario_id,
                        Aprovacao.acao["tipo"].astext == "preencher_senha",
                    )
                )
            ).all()
        assert cartao.status == StatusAprovacao.PENDENTE
        assert cartao.acao["dominio"] == "localhost" and cartao.acao["ref"] == campo_senha
        atencao = (await cliente.get("/v1/atencao", headers=auth)).json()
        item = next(p for p in atencao if p["id"] == str(cartao.id))
        assert item["acao"] == "preencher_senha"
        assert [o["valor"] for o in item["opcoes"]] == ["preencher_senha", "negar"]

        # 2) o usuário manda a senha: fica cifrada no Redis, nunca no banco
        enviado = await cliente.post(
            f"/v1/navegador/senhas/{cartao.id}", headers=auth, json={"senha": SENHA}
        )
        assert enviado.status_code == 204, enviado.text
        redis = Redis.from_url(mundo.url_redis)
        try:
            guardada = await redis.get(CHAVE_REDIS.format(cartao.id))
            assert guardada and SENHA.encode() not in guardada
            async with mundo.fabrica() as sessao:
                linha = await sessao.get(Aprovacao, cartao.id)
                assert linha is not None and linha.status == StatusAprovacao.PERMITIDA
                assert SENHA not in str(linha.acao) and SENHA not in str(linha.avaliacao)
            de_novo = await cliente.post(
                f"/v1/navegador/senhas/{cartao.id}", headers=auth, json={"senha": SENHA}
            )
            assert de_novo.status_code == 409

            # 3) o turno retoma: o campo é preenchido e o modelo só sabe que foi
            monkeypatch.setattr("langgraph.types.interrupt", lambda _valor: "permitir_uma_vez")
            resultado = await amb.executar("navegador_pedir_senha", pedido, ctx)
            assert SENHA not in str(resultado)
            assert "preenchida" in str(resultado)
            pagina = amb.motor.pagina(amb.gerente.do_agente(agente)[0])
            assert await pagina.input_value("#s") == SENHA
            assert await redis.get(CHAVE_REDIS.format(cartao.id)) is None  # lida uma vez só
            assert SENHA not in str(amb.arvore.ultimo_rastro(aba_id))
        finally:
            await redis.aclose()

        # 4) pedir de novo (senha errada, por exemplo) abre um cartão novo
        monkeypatch.setattr("langgraph.types.interrupt", pausar)
        with pytest.raises(_Pausa):
            await amb.executar("navegador_pedir_senha", pedido, ctx)
        async with mundo.fabrica() as sessao:
            cartoes = (
                await sessao.scalars(
                    select(Aprovacao).where(Aprovacao.acao["tipo"].astext == "preencher_senha")
                )
            ).all()
        assert len(cartoes) == 2

        # 5) "Eu mesmo faço": nada é preenchido e o bot é orientado a pedir que o usuário assuma
        monkeypatch.setattr("langgraph.types.interrupt", lambda _valor: "negar")
        recusa = await amb.executar("navegador_pedir_senha", pedido, ctx)
        assert "assumir a aba" in str(recusa)

        rotina = ContextoFerramenta(
            usuario_id=usuario_id, agente_id=agente, conversa_id=uuid4(), sem_supervisao=True
        )
        with pytest.raises(ErroFerramenta, match="Rotina"):
            await amb._pedir_senha(amb.gerente.do_agente(agente)[0], pedido, rotina)
