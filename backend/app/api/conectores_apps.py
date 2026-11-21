"""Catálogo de apps com login (Onda 3, item 12). Regras em ``app/conectores/oauth.py``.

- ``GET  /v1/conectores/apps``: o catálogo e o que já está conectado;
- ``POST /v1/conectores/apps/{app}/conectar``: descobre o login do app, faz o cadastro automático
  e devolve o endereço para o usuário entrar (abre em outra janela);
- ``GET  /v1/conectores/oauth/retorno`` (sem login: o ``state`` de uso único, guardado no Redis
  por 10 min, é o que liga a volta ao usuário): troca o código pelos tokens, cria (ou atualiza) o
  conector e manda o navegador de volta para Configurações → Conectores.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conectores import oauth
from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis, usuario_atual
from app.core.redis import verificar_limite
from app.ferramentas.base import ErroFerramenta
from app.modelos.tabelas import Conector, ConectorOAuth

roteador = APIRouter(prefix="/conectores", tags=["conectores"])
roteador_publico = APIRouter(prefix="/conectores/oauth", tags=["conectores"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]
RedisDep = Annotated[Redis, Depends(obter_redis)]

LIMITE_CONECTAR = (20, 60 * 60)


class AppSaida(BaseModel):
    id: str
    nome: str
    descricao: str
    categoria: str
    url: str
    conectado: bool
    conector_id: UUID | None


class ConectarSaida(BaseModel):
    url_autorizacao: str


def _retorno(requisicao: Request) -> str:
    base = (obter_configuracao().api_url or str(requisicao.base_url)).rstrip("/")
    return f"{base}/v1/conectores/oauth/retorno"


def _volta_ao_app(**parametros: str) -> RedirectResponse:
    base = obter_configuracao().app_url.rstrip("/")
    return RedirectResponse(
        f"{base}/configuracoes?{urlencode({'secao': 'conectores', **parametros})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@roteador.get("/apps")
async def listar_apps(usuario_id: UsuarioId, sessao: Sessao) -> list[AppSaida]:
    linhas = (
        await sessao.execute(
            select(ConectorOAuth.app, Conector.id)
            .join(Conector, Conector.id == ConectorOAuth.conector_id)
            .where(ConectorOAuth.usuario_id == usuario_id)
        )
    ).all()
    conectados = {app: conector_id for app, conector_id in linhas}
    return [
        AppSaida(
            id=app.id,
            nome=app.nome,
            descricao=app.descricao,
            categoria=app.categoria,
            url=app.url,
            conectado=app.id in conectados,
            conector_id=conectados.get(app.id),
        )
        for app in oauth.CATALOGO
    ]


@roteador.post("/apps/{app_id}/conectar")
async def conectar_app(
    app_id: str, requisicao: Request, usuario_id: UsuarioId, redis: RedisDep
) -> ConectarSaida:
    espera = await verificar_limite(redis, f"conectores:oauth:{usuario_id}", *LIMITE_CONECTAR)
    if espera:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Muitas tentativas de conectar. Tente mais tarde.",
            headers={"Retry-After": str(espera)},
        )
    try:
        app = oauth.app_do_catalogo(app_id)
    except ErroFerramenta as erro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(erro)) from erro
    retorno = _retorno(requisicao)
    try:
        meta = await oauth.descobrir(app.url)
        cliente = await oauth.cadastrar(meta, retorno)
    except ErroFerramenta as erro:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{app.nome}: {erro}") from erro
    estado = secrets.token_urlsafe(32)
    verificador, desafio = oauth.pkce()
    await redis.set(
        oauth.CHAVE_ESTADO.format(estado),
        json.dumps(
            {
                "usuario_id": str(usuario_id),
                "app": app.id,
                "verificador": verificador,
                "cliente": cliente.model_dump(),
                "token_endpoint": meta.token_endpoint,
                "recurso": meta.resource,
                "retorno": retorno,
            }
        ),
        ex=oauth.VALIDADE_ESTADO_S,
    )
    return ConectarSaida(
        url_autorizacao=oauth.url_de_autorizacao(meta, cliente, retorno, estado, desafio)
    )


@roteador_publico.get("/retorno", include_in_schema=False)
async def retorno_do_login(
    sessao: Sessao,
    redis: RedisDep,
    state: str = "",
    code: str = "",
    error: str = "",
) -> RedirectResponse:
    from app.conectores.ferramenta import criar_conector

    bruto = await redis.getdel(oauth.CHAVE_ESTADO.format(state)) if state else None
    if not bruto:
        return _volta_ao_app(resultado="erro", mensagem="O login expirou. Tente conectar de novo.")
    pedido = json.loads(bruto)
    app = oauth.app_do_catalogo(pedido["app"])
    if error or not code:
        return _volta_ao_app(
            resultado="erro", app=app.id, mensagem=f"O login no {app.nome} foi cancelado."
        )
    usuario_id = UUID(pedido["usuario_id"])
    cliente = oauth.Cliente.model_validate(pedido["cliente"])
    try:
        tokens = await oauth.trocar_codigo(
            pedido["token_endpoint"],
            cliente,
            code,
            pedido["verificador"],
            pedido["retorno"],
            pedido["recurso"],
        )
    except ErroFerramenta as erro:
        return _volta_ao_app(resultado="erro", app=app.id, mensagem=f"{app.nome}: {erro}")
    dados = oauth.DadosOAuth(
        cliente=cliente,
        token_endpoint=pedido["token_endpoint"],
        recurso=pedido["recurso"],
        tokens=tokens,
    )
    existente = await sessao.scalar(
        select(ConectorOAuth).where(
            ConectorOAuth.usuario_id == usuario_id, ConectorOAuth.app == app.id
        )
    )
    if existente is not None:
        existente.dados_cifrados = oauth.cifrar(usuario_id, existente.conector_id, dados)
        existente.expira_em = tokens.expira_em
        existente.atualizado_em = datetime.now(UTC)
        conector = await sessao.get(Conector, existente.conector_id)
        if conector is not None:
            conector.ativo = True
    else:
        try:
            conector = await criar_conector(sessao, usuario_id, app.nome, app.url, {})
        except ErroFerramenta as erro:
            return _volta_ao_app(resultado="erro", app=app.id, mensagem=str(erro))
        sessao.add(
            ConectorOAuth(
                conector_id=conector.id,
                usuario_id=usuario_id,
                app=app.id,
                dados_cifrados=oauth.cifrar(usuario_id, conector.id, dados),
                expira_em=tokens.expira_em,
            )
        )
    await sessao.commit()
    return _volta_ao_app(resultado="conectado", app=app.id)
