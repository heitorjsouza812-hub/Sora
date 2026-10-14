"""Rotas de cadastro, login, renovação e saída; especificação §8.2.

Web: o token de renovação vai num cookie httpOnly. Desktop (`X-Sora-Cliente: desktop`): vai no
corpo, porque o cookie `Lax` não acompanha pedidos de `http://tauri.localhost`.
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import contas, seguranca
from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis
from app.modelos.esquemas import CadastroEntrada, LoginEntrada, RenovacaoEntrada, TokensSaida

roteador = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_RENOVACAO = "sora_renovacao"
CAMINHO_COOKIE = "/v1/auth"

Sessao = Annotated[AsyncSession, Depends(obter_sessao)]
RedisDep = Annotated[Redis, Depends(obter_redis)]
ClienteCabecalho = Annotated[str | None, Header(alias=contas.CABECALHO_CLIENTE)]


def _ip(requisicao: Request) -> str | None:
    return requisicao.client.host if requisicao.client else None


def _responder_tokens(
    resposta: Response, cliente: str, token_renovacao: str, token_acesso: str
) -> TokensSaida:
    if cliente == contas.CLIENTE_DESKTOP:
        return TokensSaida(token_acesso=token_acesso, token_renovacao=token_renovacao)
    resposta.set_cookie(
        COOKIE_RENOVACAO,
        token_renovacao,
        max_age=int(seguranca.RENOVACAO_VALIDADE.total_seconds()),
        path=CAMINHO_COOKIE,
        httponly=True,
        secure=obter_configuracao().ambiente == "producao",
        samesite="lax",
    )
    return TokensSaida(token_acesso=token_acesso)


@roteador.post("/cadastrar", status_code=status.HTTP_201_CREATED)
async def cadastrar(
    dados: CadastroEntrada, requisicao: Request, sessao: Sessao, redis: RedisDep
) -> None:
    """Cadastra uma conta mediante convite."""
    await contas.cadastrar(sessao, redis, dados, _ip(requisicao))


@roteador.post("/entrar")
async def entrar(
    dados: LoginEntrada,
    requisicao: Request,
    resposta: Response,
    sessao: Sessao,
    redis: RedisDep,
    x_sora_cliente: ClienteCabecalho = None,
) -> TokensSaida:
    """Autentica e devolve os tokens adequados ao cliente."""
    cliente = contas.cliente_da_requisicao(x_sora_cliente)
    renovacao, acesso = await contas.entrar(
        sessao, redis, dados, cliente, _ip(requisicao), requisicao.headers.get("user-agent")
    )
    return _responder_tokens(resposta, cliente, renovacao, acesso)


@roteador.post("/renovar")
async def renovar(
    resposta: Response,
    sessao: Sessao,
    dados: RenovacaoEntrada | None = None,
    cookie_renovacao: Annotated[str | None, Cookie(alias=COOKIE_RENOVACAO)] = None,
) -> TokensSaida:
    """Rotaciona o token de renovação e emite novo acesso."""
    token = (dados.token_renovacao if dados else None) or cookie_renovacao
    renovacao, acesso, cliente = await contas.renovar(sessao, token)
    return _responder_tokens(resposta, cliente, renovacao, acesso)


@roteador.post("/sair", status_code=status.HTTP_204_NO_CONTENT)
async def sair(
    resposta: Response,
    sessao: Sessao,
    dados: RenovacaoEntrada | None = None,
    cookie_renovacao: Annotated[str | None, Cookie(alias=COOKIE_RENOVACAO)] = None,
) -> None:
    """Encerra a sessão atual e remove o cookie quando aplicável."""
    token = (dados.token_renovacao if dados else None) or cookie_renovacao
    await contas.sair(sessao, token)
    resposta.delete_cookie(COOKIE_RENOVACAO, path=CAMINHO_COOKIE)
