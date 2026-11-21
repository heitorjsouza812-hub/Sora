"""Catálogo de apps com login (Onda 3, item 12): regras puras de ``app/conectores/oauth.py``."""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest

from app.conectores import oauth
from app.ferramentas.base import ErroFerramenta


def test_catalogo_so_tem_https_e_ids_unicos() -> None:
    ids = [app.id for app in oauth.CATALOGO]
    assert len(ids) == len(set(ids)) == 15
    assert all(app.url.startswith("https://") for app in oauth.CATALOGO)
    assert oauth.app_do_catalogo("canva").nome == "Canva"
    with pytest.raises(ErroFerramenta):
        oauth.app_do_catalogo("nao-existe")


def test_pkce_s256() -> None:
    verificador, desafio = oauth.pkce()
    esperado = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest())
    assert desafio == esperado.decode().rstrip("=")
    assert 43 <= len(verificador) <= 128
    assert oauth.pkce()[0] != verificador


def test_endereco_de_autorizacao_leva_pkce_state_e_recurso() -> None:
    meta = oauth.Metadados(
        resource="https://mcp.app.exemplo/mcp",
        authorization_endpoint="https://app.exemplo/oauth/authorize?tenant=1",
        token_endpoint="https://app.exemplo/oauth/token",
        registration_endpoint="https://app.exemplo/oauth/register",
        scopes=["ler", "escrever"],
    )
    url = oauth.url_de_autorizacao(
        meta,
        oauth.Cliente(client_id="cli"),
        "https://sora.exemplo/v1/conectores/oauth/retorno",
        "est",
        "des",
    )
    assert url.startswith("https://app.exemplo/oauth/authorize?tenant=1&")
    q = parse_qs(urlsplit(url).query)
    assert q["response_type"] == ["code"] and q["client_id"] == ["cli"]
    assert q["code_challenge"] == ["des"] and q["code_challenge_method"] == ["S256"]
    assert q["state"] == ["est"] and q["resource"] == ["https://mcp.app.exemplo/mcp"]
    assert q["scope"] == ["ler escrever"]


def test_recusa_endereco_sem_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.conectores.ferramenta.ambiente_local", lambda: False)
    with pytest.raises(ErroFerramenta, match="https"):
        oauth._conferir_url("http://app.exemplo/token")
    with pytest.raises(ErroFerramenta):
        oauth._conferir_url("http://localhost:9000/token")  # em produção, nem localhost
    assert oauth._conferir_url("https://app.exemplo/token") == "https://app.exemplo/token"
