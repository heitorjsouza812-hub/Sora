# ruff: noqa: F811
"""Catálogo de apps com login (Onda 3, item 12) com Postgres, Redis e a API reais, e um servidor
OAuth + MCP falso em 127.0.0.1 (fora de produção o ``http://localhost`` é aceito).

Prova o fluxo inteiro da especificação de autorização do MCP: 401 com ``resource_metadata`` →
metadados → cadastro automático → autorização com PKCE (o servidor falso confere o desafio) →
troca do código → conector criado com o token cifrado → ``Authorization: Bearer`` → renovação.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from sqlalchemy import select

from app.conectores import oauth
from app.modelos.tabelas import Conector, ConectorOAuth
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


class _Estado:
    porta = 0
    desafio = ""
    concessoes: ClassVar[list[dict[str, list[str]]]] = []
    cadastros: ClassVar[list[dict[str, Any]]] = []


def _base() -> str:
    return f"http://127.0.0.1:{_Estado.porta}"


class _Servidor(BaseHTTPRequestHandler):
    def _json(
        self, codigo: int, dados: dict[str, Any], extra: dict[str, str] | None = None
    ) -> None:
        corpo = json.dumps(dados).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        for chave, valor in (extra or {}).items():
            self.send_header(chave, valor)
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_GET(self) -> None:
        caminho = urlsplit(self.path)
        if caminho.path == "/.well-known/oauth-protected-resource/mcp":
            self._json(
                200,
                {
                    "resource": f"{_base()}/mcp",
                    "authorization_servers": [_base()],
                    "scopes_supported": ["ler"],
                },
            )
        elif caminho.path == "/.well-known/oauth-authorization-server":
            self._json(
                200,
                {
                    "issuer": _base(),
                    "authorization_endpoint": f"{_base()}/authorize",
                    "token_endpoint": f"{_base()}/token",
                    "registration_endpoint": f"{_base()}/register",
                    "code_challenge_methods_supported": ["S256"],
                },
            )
        elif caminho.path == "/authorize":
            q = parse_qs(caminho.query)
            _Estado.desafio = q["code_challenge"][0]
            destino = (
                q["redirect_uri"][0]
                + "?"
                + urlencode({"code": "codigo-ok", "state": q["state"][0]})
            )
            self.send_response(302)
            self.send_header("Location", destino)
            self.end_headers()
        else:
            self._json(404, {})

    def do_POST(self) -> None:
        caminho = urlsplit(self.path).path
        if caminho == "/mcp":
            cabecalho = (
                f'Bearer resource_metadata="{_base()}/.well-known/oauth-protected-resource/mcp"'
            )
            self._json(401, {"error": "login"}, {"WWW-Authenticate": cabecalho})
        elif caminho == "/register":
            dados = json.loads(self._corpo())
            _Estado.cadastros.append(dados)
            self._json(201, {"client_id": "cli-1", "redirect_uris": dados["redirect_uris"]})
        elif caminho == "/token":
            campos = parse_qs(self._corpo().decode())
            _Estado.concessoes.append(campos)
            if campos["grant_type"] == ["authorization_code"]:
                verificador = campos["code_verifier"][0]
                calculado = (
                    base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest())
                    .decode()
                    .rstrip("=")
                )
                if campos["code"] != ["codigo-ok"] or calculado != _Estado.desafio:
                    self._json(400, {"error": "invalid_grant"})
                    return
                self._json(
                    200,
                    {"access_token": "tok-1", "refresh_token": "ref-1", "expires_in": 3600},
                )
            elif campos["grant_type"] == ["refresh_token"] and campos["refresh_token"] == ["ref-1"]:
                self._json(200, {"access_token": "tok-2", "expires_in": 3600})
            else:
                self._json(400, {"error": "invalid_grant"})
        else:
            self._json(404, {})

    def log_message(self, *_a: Any) -> None:
        return


@pytest.fixture
def app_falso(monkeypatch: pytest.MonkeyPatch):
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Servidor)
    _Estado.porta = servidor.server_address[1]
    _Estado.concessoes, _Estado.cadastros = [], []
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    app = oauth.AppCatalogo("teste", "App Teste", f"{_base()}/mcp", "Para testar.", "Teste")
    monkeypatch.setattr(oauth, "CATALOGO", (*oauth.CATALOGO, app))
    yield app
    servidor.shutdown()


async def test_conectar_app_pelo_login_oauth(mundo: Mundo, app_falso: oauth.AppCatalogo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "apps-oauth@exemplo.com")
        catalogo = (await cliente.get("/v1/conectores/apps", headers=auth)).json()
        assert {a["id"] for a in catalogo} >= {"canva", "mercado-pago", "notion", "teste"}
        assert next(a for a in catalogo if a["id"] == "teste")["conectado"] is False
        assert (
            await cliente.post("/v1/conectores/apps/nao-existe/conectar", headers=auth)
        ).status_code == 404

        inicio = await cliente.post("/v1/conectores/apps/teste/conectar", headers=auth)
        assert inicio.status_code == 200, inicio.text
        url = inicio.json()["url_autorizacao"]
        q = parse_qs(urlsplit(url).query)
        retorno = f"{mundo.url}/v1/conectores/oauth/retorno"
        assert url.startswith(f"{_base()}/authorize?")
        assert q["client_id"] == ["cli-1"] and q["redirect_uri"] == [retorno]
        assert q["code_challenge_method"] == ["S256"] and q["resource"] == [f"{_base()}/mcp"]
        assert q["scope"] == ["ler"]
        assert _Estado.cadastros[0]["redirect_uris"] == [retorno]
        assert _Estado.cadastros[0]["token_endpoint_auth_method"] == "none"

        # o usuário entra no app (o servidor falso volta direto com o código)
        async with httpx.AsyncClient(timeout=30) as navegador:
            ida = await navegador.get(url)
            assert ida.status_code == 302
            volta = await navegador.get(ida.headers["location"])
        assert volta.status_code == 303
        destino = volta.headers["location"]
        assert destino.startswith("http://localhost:5173/configuracoes?")
        assert parse_qs(urlsplit(destino).query)["resultado"] == ["conectado"]
        # o state é de uso único
        async with httpx.AsyncClient(timeout=30) as navegador:
            repetida = await navegador.get(ida.headers["location"])
        assert "expirou" in parse_qs(urlsplit(repetida.headers["location"]).query)["mensagem"][0]

        conectado = next(
            a
            for a in (await cliente.get("/v1/conectores/apps", headers=auth)).json()
            if a["id"] == "teste"
        )
        assert conectado["conectado"] is True and conectado["conector_id"]
        lista = (await cliente.get("/v1/conectores", headers=auth)).json()
        assert [c["nome"] for c in lista] == ["App Teste"]

    async with mundo.fabrica() as sessao:
        linha = await sessao.scalar(select(ConectorOAuth))
        assert linha is not None and linha.app == "teste"
        assert b"tok-1" not in linha.dados_cifrados and b"ref-1" not in linha.dados_cifrados
        conector = await sessao.get(Conector, linha.conector_id)
        assert conector is not None and conector.cabecalhos_cifrados is None
        cabecalhos = await oauth.cabecalhos_do_conector(sessao, conector)
        assert cabecalhos == {"Authorization": "Bearer tok-1"}

        # perto de vencer: renova com o refresh_token e guarda o novo (o refresh antigo fica)
        dados = oauth.decifrar(linha.usuario_id, linha.conector_id, linha.dados_cifrados)
        vencido = dados.tokens.model_copy(
            update={"expira_em": datetime.now(UTC) + timedelta(seconds=10)}
        )
        linha.dados_cifrados = oauth.cifrar(
            linha.usuario_id, linha.conector_id, dados.model_copy(update={"tokens": vencido})
        )
        await sessao.flush()
        cabecalhos = await oauth.cabecalhos_do_conector(sessao, conector)
        assert cabecalhos == {"Authorization": "Bearer tok-2"}
        assert _Estado.concessoes[-1]["grant_type"] == ["refresh_token"]
        guardado = oauth.decifrar(linha.usuario_id, linha.conector_id, linha.dados_cifrados)
        assert guardado.tokens.access_token == "tok-2" and guardado.tokens.refresh_token == "ref-1"
        await sessao.commit()
