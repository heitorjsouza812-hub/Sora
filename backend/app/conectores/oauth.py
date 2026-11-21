"""Catálogo de apps com login (Onda 3, item 12; ideia vista no OpenBot, escrita do zero).

Cada app do catálogo é um servidor MCP **oficial** que aceita login OAuth 2.1 com cadastro
automático do cliente (RFC 7591) e PKCE S256, conferidos nos metadados públicos de cada um em
2026-11-20. Assim a Sora não precisa de chave de cliente cadastrada em cada empresa.

Fluxo (especificação de autorização do MCP):

1. **descobrir**: ``POST`` sem token no servidor → ``401`` com ``resource_metadata`` (RFC 9728),
   ou o ``/.well-known/oauth-protected-resource``; dali o servidor de autorização e os metadados
   dele (RFC 8414 / OpenID), com ``authorization_endpoint``, ``token_endpoint`` e
   ``registration_endpoint``;
2. **cadastrar**: ``POST registration_endpoint`` com o endereço de retorno da Sora;
3. **autorizar**: o navegador do usuário vai ao ``authorization_endpoint`` com PKCE, ``state`` e
   ``resource`` (RFC 8707); volta em ``/v1/conectores/oauth/retorno``;
4. **trocar**: código → ``access_token`` (+ ``refresh_token``), guardados **cifrados**;
5. **usar**: o worker manda ``Authorization: Bearer`` ao servidor MCP e renova o token perto de
   vencer (``cabecalhos_do_conector``).

Toda chamada do servidor (metadados, cadastro, token) só vai a ``https`` com IP público (o mesmo
transporte do ``ler_pagina``); ``http://localhost`` só fora de produção.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ferramentas.base import ErroFerramenta

PRAZO_S = 15.0
VALIDADE_ESTADO_S = 10 * 60
RENOVAR_ANTES = timedelta(seconds=90)
CHAVE_ESTADO = "conectores:oauth:estado:{}"
NOME_DO_CLIENTE = "Sora"
_LOCAIS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True, slots=True)
class AppCatalogo:
    id: str
    nome: str
    url: str
    descricao: str
    categoria: str


CATALOGO: tuple[AppCatalogo, ...] = (
    AppCatalogo("canva", "Canva", "https://mcp.canva.com/mcp", "Criar e editar designs.", "Design"),
    AppCatalogo(
        "mercado-pago",
        "Mercado Pago",
        "https://mcp.mercadopago.com/mcp",
        "Consultar pagamentos e vendas.",
        "Vendas",
    ),
    AppCatalogo("notion", "Notion", "https://mcp.notion.com/mcp", "Páginas e bases.", "Docs"),
    AppCatalogo("dropbox", "Dropbox", "https://mcp.dropbox.com/mcp", "Seus arquivos.", "Arquivos"),
    AppCatalogo("wix", "Wix", "https://mcp.wix.com/mcp", "Site e loja no Wix.", "Site"),
    AppCatalogo("webflow", "Webflow", "https://mcp.webflow.com/mcp", "Site no Webflow.", "Site"),
    AppCatalogo(
        "monday", "monday.com", "https://mcp.monday.com/mcp", "Quadros e tarefas.", "Tarefas"
    ),
    AppCatalogo("clickup", "ClickUp", "https://mcp.clickup.com/mcp", "Tarefas e docs.", "Tarefas"),
    AppCatalogo("todoist", "Todoist", "https://ai.todoist.net/mcp", "Lista de tarefas.", "Tarefas"),
    AppCatalogo(
        "airtable", "Airtable", "https://mcp.airtable.com/mcp", "Bases e planilhas.", "Dados"
    ),
    AppCatalogo("miro", "Miro", "https://mcp.miro.com/", "Quadros colaborativos.", "Design"),
    AppCatalogo("figma", "Figma", "https://mcp.figma.com/mcp", "Arquivos de design.", "Design"),
    AppCatalogo(
        "zapier", "Zapier", "https://mcp.zapier.com/api/mcp/mcp", "Automações.", "Automação"
    ),
    AppCatalogo("make", "Make", "https://mcp.make.com", "Cenários de automação.", "Automação"),
    AppCatalogo("stripe", "Stripe", "https://mcp.stripe.com", "Pagamentos e clientes.", "Vendas"),
)


def app_do_catalogo(app_id: str) -> AppCatalogo:
    for app in CATALOGO:
        if app.id == app_id:
            return app
    raise ErroFerramenta("App não encontrado no catálogo.")


class Metadados(BaseModel):
    resource: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str
    scopes: list[str] = []


class Cliente(BaseModel):
    client_id: str
    client_secret: str | None = None
    metodo: str = "none"
    """``none``, ``client_secret_post`` ou ``client_secret_basic``."""


class Tokens(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expira_em: datetime | None = None


# ---------------------------------------------------------------- HTTP seguro


def _local_permitido(url: str) -> bool:
    from app.conectores.ferramenta import ambiente_local

    return ambiente_local() and (urlsplit(url).hostname or "") in _LOCAIS


def _conferir_url(url: str) -> str:
    """Só ``https`` (``http://localhost`` fora de produção), sem usuário e senha na URL."""
    from app.busca.ler_pagina import EnderecoBloqueado, ErroLeitura, validar_url

    try:
        alvo = validar_url(url)
    except (EnderecoBloqueado, ErroLeitura) as erro:
        raise ErroFerramenta("O app devolveu um endereço inválido.") from erro
    if alvo.scheme != "https" and not _local_permitido(str(alvo)):
        raise ErroFerramenta("O app devolveu um endereço sem https.")
    return str(alvo)


def _cliente_http(url: str) -> httpx.AsyncClient:
    if _local_permitido(url):
        return httpx.AsyncClient(timeout=PRAZO_S, follow_redirects=False, trust_env=False)
    from app.conectores.servidores import fabrica_cliente_seguro

    return fabrica_cliente_seguro(timeout=httpx.Timeout(PRAZO_S))


async def _pedir(metodo: str, url: str, **kwargs: Any) -> httpx.Response:
    """Uma chamada, seguindo até 3 redirecionamentos conferidos (cada destino é revalidado)."""
    for _ in range(4):
        url = _conferir_url(url)
        async with _cliente_http(url) as http:
            resposta = await http.request(metodo, url, **kwargs)
        if resposta.status_code in (301, 302, 303, 307, 308) and "location" in resposta.headers:
            url = str(httpx.URL(url).join(resposta.headers["location"]))
            if resposta.status_code == 303:
                metodo, kwargs = "GET", {}
            continue
        return resposta
    raise ErroFerramenta("O app redirecionou demais.")


async def _json(url: str) -> dict[str, Any] | None:
    try:
        resposta = await _pedir("GET", url, headers={"Accept": "application/json"})
    except (httpx.HTTPError, ErroFerramenta):
        return None
    if resposta.status_code != 200:
        return None
    try:
        dados = resposta.json()
    except ValueError:
        return None
    return dados if isinstance(dados, dict) else None


# ---------------------------------------------------------------- 1. descobrir


async def descobrir(url_servidor: str) -> Metadados:
    partes = urlsplit(url_servidor)
    origem = f"{partes.scheme}://{partes.netloc}"
    caminho = partes.path.rstrip("/")
    candidatos: list[str] = []
    try:
        resposta = await _pedir(
            "POST",
            url_servidor,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": NOME_DO_CLIENTE, "version": "1"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
        achado = re.search(
            r'resource_metadata="([^"]+)"', resposta.headers.get("www-authenticate", "")
        )
        if achado:
            candidatos.append(achado.group(1))
    except (httpx.HTTPError, ErroFerramenta):
        pass
    if caminho:
        candidatos.append(f"{origem}/.well-known/oauth-protected-resource{caminho}")
    candidatos.append(f"{origem}/.well-known/oauth-protected-resource")
    recurso: dict[str, Any] = {}
    for url in candidatos:
        dados = await _json(url)
        if dados and dados.get("authorization_servers"):
            recurso = dados
            break
    servidores = [str(s) for s in recurso.get("authorization_servers") or [origem]][:3]
    autorizacao: dict[str, Any] | None = None
    for servidor in servidores:
        base = servidor.rstrip("/")
        p = urlsplit(base)
        raiz, sufixo = f"{p.scheme}://{p.netloc}", p.path.rstrip("/")
        for url in (
            f"{raiz}/.well-known/oauth-authorization-server{sufixo}",
            f"{raiz}/.well-known/openid-configuration{sufixo}",
            f"{base}/.well-known/openid-configuration",
            f"{raiz}/.well-known/oauth-authorization-server",
        ):
            dados = await _json(url)
            if dados and dados.get("authorization_endpoint") and dados.get("token_endpoint"):
                autorizacao = dados
                break
        if autorizacao:
            break
    if not autorizacao:
        raise ErroFerramenta("Não achei o login deste app. Tente de novo mais tarde.")
    if not autorizacao.get("registration_endpoint"):
        raise ErroFerramenta("Este app não aceita o cadastro automático da Sora.")
    metodos = autorizacao.get("code_challenge_methods_supported") or ["S256"]
    if "S256" not in metodos:
        raise ErroFerramenta("Este app não oferece um login seguro (PKCE) para a Sora.")
    return Metadados(
        resource=str(recurso.get("resource") or url_servidor),
        authorization_endpoint=_conferir_url(str(autorizacao["authorization_endpoint"])),
        token_endpoint=_conferir_url(str(autorizacao["token_endpoint"])),
        registration_endpoint=_conferir_url(str(autorizacao["registration_endpoint"])),
        scopes=[str(s) for s in (recurso.get("scopes_supported") or [])][:20],
    )


# ---------------------------------------------------------------- 2. cadastrar


async def cadastrar(meta: Metadados, retorno: str) -> Cliente:
    corpo = {
        "client_name": NOME_DO_CLIENTE,
        "redirect_uris": [retorno],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    try:
        resposta = await _pedir("POST", meta.registration_endpoint, json=corpo)
    except httpx.HTTPError as erro:
        raise ErroFerramenta("Não consegui falar com o app para fazer o cadastro.") from erro
    if resposta.status_code not in (200, 201):
        raise ErroFerramenta(f"O app recusou o cadastro da Sora (erro {resposta.status_code}).")
    try:
        dados = resposta.json()
    except ValueError as erro:
        raise ErroFerramenta("O app respondeu o cadastro de um jeito ilegível.") from erro
    if not isinstance(dados, dict) or not dados.get("client_id"):
        raise ErroFerramenta("O app não devolveu a identificação do cadastro.")
    segredo = dados.get("client_secret")
    metodo = str(
        dados.get("token_endpoint_auth_method") or ("client_secret_post" if segredo else "none")
    )
    return Cliente(client_id=str(dados["client_id"]), client_secret=segredo, metodo=metodo)


# ---------------------------------------------------------------- 3. autorizar


def pkce() -> tuple[str, str]:
    """``(verificador, desafio)`` S256."""
    verificador = secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest())
    return verificador, desafio.decode().rstrip("=")


def url_de_autorizacao(
    meta: Metadados, cliente: Cliente, retorno: str, estado: str, desafio: str
) -> str:
    parametros = {
        "response_type": "code",
        "client_id": cliente.client_id,
        "redirect_uri": retorno,
        "state": estado,
        "code_challenge": desafio,
        "code_challenge_method": "S256",
        "resource": meta.resource,
    }
    if meta.scopes:
        parametros["scope"] = " ".join(meta.scopes)
    separador = "&" if "?" in meta.authorization_endpoint else "?"
    return f"{meta.authorization_endpoint}{separador}{urlencode(parametros)}"


# ---------------------------------------------------------------- 4/5. tokens


async def _pedir_token(token_endpoint: str, cliente: Cliente, campos: dict[str, str]) -> Tokens:
    corpo = {**campos, "client_id": cliente.client_id}
    autenticacao = None
    if cliente.client_secret:
        if cliente.metodo == "client_secret_basic":
            autenticacao = (cliente.client_id, cliente.client_secret)
        else:
            corpo["client_secret"] = cliente.client_secret
    try:
        resposta = await _pedir(
            "POST",
            token_endpoint,
            data=corpo,
            headers={"Accept": "application/json"},
            auth=autenticacao,
        )
    except httpx.HTTPError as erro:
        raise ErroFerramenta("Não consegui falar com o app para entrar.") from erro
    if resposta.status_code != 200:
        raise ErroFerramenta(f"O app recusou o login (erro {resposta.status_code}).")
    try:
        dados = resposta.json()
    except ValueError as erro:
        raise ErroFerramenta("O app respondeu o login de um jeito ilegível.") from erro
    if not isinstance(dados, dict) or not dados.get("access_token"):
        raise ErroFerramenta("O app não devolveu o acesso.")
    expira = None
    if isinstance(dados.get("expires_in"), int | float) and dados["expires_in"] > 0:
        expira = datetime.now(UTC) + timedelta(seconds=float(dados["expires_in"]))
    return Tokens(
        access_token=str(dados["access_token"]),
        refresh_token=str(dados["refresh_token"]) if dados.get("refresh_token") else None,
        expira_em=expira,
    )


async def trocar_codigo(
    token_endpoint: str, cliente: Cliente, codigo: str, verificador: str, retorno: str, recurso: str
) -> Tokens:
    return await _pedir_token(
        token_endpoint,
        cliente,
        {
            "grant_type": "authorization_code",
            "code": codigo,
            "redirect_uri": retorno,
            "code_verifier": verificador,
            "resource": recurso,
        },
    )


async def renovar(
    token_endpoint: str, cliente: Cliente, refresh_token: str, recurso: str
) -> Tokens:
    tokens = await _pedir_token(
        token_endpoint,
        cliente,
        {"grant_type": "refresh_token", "refresh_token": refresh_token, "resource": recurso},
    )
    if tokens.refresh_token is None:
        tokens = tokens.model_copy(update={"refresh_token": refresh_token})
    return tokens


# ---------------------------------------------------------------- guardar e usar


class DadosOAuth(BaseModel):
    """O que fica cifrado em ``conectores_oauth.dados_cifrados``."""

    cliente: Cliente
    token_endpoint: str
    recurso: str
    tokens: Tokens


def _provedor_cifra(conector_id: UUID) -> str:
    return f"conector-oauth:{conector_id}"


def cifrar(usuario_id: UUID, conector_id: UUID, dados: DadosOAuth) -> bytes:
    from app.core.seguranca import cifrar_segredo

    return cifrar_segredo(
        dados.model_dump_json(), usuario_id=usuario_id, provedor=_provedor_cifra(conector_id)
    )


def decifrar(usuario_id: UUID, conector_id: UUID, bruto: bytes) -> DadosOAuth:
    from app.core.seguranca import decifrar_segredo

    texto = decifrar_segredo(bruto, usuario_id=usuario_id, provedor=_provedor_cifra(conector_id))
    return DadosOAuth.model_validate(json.loads(texto))


async def cabecalhos_do_conector(sessao: AsyncSession, conector: Any) -> dict[str, str]:
    """Cabeçalhos do conector para o worker e para o "Testar": os gravados à mão e, se ele veio
    do catálogo, o ``Authorization: Bearer`` (renovado quando falta pouco para vencer)."""
    from app.conectores.ferramenta import decifrar_cabecalhos
    from app.modelos.tabelas import ConectorOAuth

    cabecalhos = decifrar_cabecalhos(conector)
    linha = await sessao.scalar(
        select(ConectorOAuth).where(ConectorOAuth.conector_id == conector.id).with_for_update()
    )
    if linha is None:
        return cabecalhos
    dados = decifrar(linha.usuario_id, linha.conector_id, linha.dados_cifrados)
    vence = dados.tokens.expira_em
    if vence is not None and vence - RENOVAR_ANTES <= datetime.now(UTC):
        if not dados.tokens.refresh_token:
            raise ErroFerramenta(f"O login de {conector.nome} venceu. Conecte de novo.")
        novos = await renovar(
            dados.token_endpoint, dados.cliente, dados.tokens.refresh_token, dados.recurso
        )
        dados = dados.model_copy(update={"tokens": novos})
        linha.dados_cifrados = cifrar(linha.usuario_id, linha.conector_id, dados)
        linha.expira_em = novos.expira_em
        linha.atualizado_em = datetime.now(UTC)
        await sessao.flush()
    return {**cabecalhos, "Authorization": f"Bearer {dados.tokens.access_token}"}
