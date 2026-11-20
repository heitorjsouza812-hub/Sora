"""Rotas de cadastro, login, renovação e saída; especificação §8.2.

Web: o token de renovação vai num cookie httpOnly. Desktop (`X-Sora-Cliente: desktop`): vai no
corpo, porque o cookie `Lax` não acompanha pedidos de `http://tauri.localhost`.
"""

import logging
from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import contas, seguranca
from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis, obter_redis_opcional
from app.modelos.esquemas import (
    CadastroEntrada,
    EsqueciSenhaEntrada,
    LoginEntrada,
    RedefinirSenhaEntrada,
    RenovacaoEntrada,
    TokensSaida,
)

roteador = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_RENOVACAO = "sora_renovacao"
CAMINHO_COOKIE = "/v1/auth"

# scope="function": o commit da sessão acontece ANTES de a resposta ser enviada. Com o escopo de
# requisição, o cliente recebia 201/200 e o commit vinha depois (e podia falhar).
Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]
RedisOpcional = Annotated[Redis | None, Depends(obter_redis_opcional)]
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
    redis: RedisOpcional,
    dados: RenovacaoEntrada | None = None,
    cookie_renovacao: Annotated[str | None, Cookie(alias=COOKIE_RENOVACAO)] = None,
) -> TokensSaida:
    """Rotaciona o token de renovação e emite novo acesso."""
    token = (dados.token_renovacao if dados else None) or cookie_renovacao
    renovacao, acesso, cliente = await contas.renovar(sessao, token, redis)
    return _responder_tokens(resposta, cliente, renovacao, acesso)


async def soltar_pc_das_sessoes(
    redis: Redis | None, usuario_id: UUID, sessoes: Sequence[UUID]
) -> None:
    """O controle do PC preso a um login (app de desktop) solta assim que o login acaba (Cerca B3).

    Falha aqui não derruba a rota: o PC solta também quando a sessão dele vence."""
    if redis is None or not sessoes:
        return
    from app.computador.pc_usuario_canal import CanalPc

    canal = CanalPc(redis)
    for sessao_id in sessoes:
        try:
            await canal.encerrar_da_sessao_de_login(usuario_id, sessao_id)
        except Exception:
            logging.getLogger(__name__).warning("não consegui soltar o PC do login", exc_info=True)


@roteador.post("/sair", status_code=status.HTTP_204_NO_CONTENT)
async def sair(
    resposta: Response,
    sessao: Sessao,
    redis: RedisOpcional,
    dados: RenovacaoEntrada | None = None,
    cookie_renovacao: Annotated[str | None, Cookie(alias=COOKIE_RENOVACAO)] = None,
) -> None:
    """Encerra a sessão atual e remove o cookie quando aplicável."""
    token = (dados.token_renovacao if dados else None) or cookie_renovacao
    encerrada = await contas.sair(sessao, token, redis)
    resposta.delete_cookie(COOKIE_RENOVACAO, path=CAMINHO_COOKIE)
    if encerrada is not None:
        await soltar_pc_das_sessoes(redis, encerrada.usuario_id, [encerrada.id])


@roteador.post("/esqueci-senha", status_code=status.HTTP_202_ACCEPTED)
async def esqueci_senha(dados: EsqueciSenhaEntrada, requisicao: Request, redis: RedisDep) -> None:
    """Pede o link de senha nova. Responde 202 sempre (exista a conta ou não); quem procura a
    conta, cria o token e envia o e-mail é o worker, então nem o tempo de resposta revela nada."""
    if not obter_configuracao().email_ligado:
        raise contas.ErroEmailDesligado()
    await contas.limitar_pedido_de_link(redis, dados.email, _ip(requisicao))
    from workers.fila import enfileirar

    await enfileirar("enviar_link_de_senha_nova", email=contas.normalizar_email(dados.email))


@roteador.post("/redefinir-senha", status_code=status.HTTP_204_NO_CONTENT)
async def redefinir_senha(
    dados: RedefinirSenhaEntrada, requisicao: Request, sessao: Sessao, redis: RedisDep
) -> None:
    """Cria a senha nova pelo link do e-mail e encerra todas as sessões da conta."""
    usuario_id, encerradas = await contas.redefinir_senha(
        sessao, redis, dados.token, dados.senha_nova, _ip(requisicao)
    )
    await soltar_pc_das_sessoes(redis, usuario_id, encerradas)
