"""Dependências compartilhadas pelas rotas protegidas; especificação §§2 e 8.2."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.seguranca import ErroToken, decodificar_token_acesso

esquema_bearer = HTTPBearer(
    scheme_name="BearerAuth",
    bearerFormat="JWT",
    description="Token de acesso emitido por /v1/auth/entrar ou /v1/auth/renovar.",
)


async def usuario_atual(
    requisicao: Request,
    credenciais: Annotated[HTTPAuthorizationCredentials, Depends(esquema_bearer)],
) -> UUID:
    """Valida o JWT de `Authorization: Bearer` e devolve o id do usuário.

    Guarda o ``exp`` do token em ``request.state.token_expira_em`` (epoch): o SSE fecha o
    stream quando o token vence (API-08/VAL-10).
    """
    try:
        carga = decodificar_token_acesso(credenciais.credentials)
        usuario_id = UUID(carga["sub"])
        requisicao.state.token_expira_em = float(carga["exp"])
        return usuario_id
    except (ErroToken, KeyError, ValueError, TypeError) as erro:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token de acesso inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from erro


def obter_redis(requisicao: Request) -> Redis:
    """Cliente Redis criado no lifespan da aplicação (`app.state.redis`)."""
    return requisicao.app.state.redis


async def exigir_provedor_validado(
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(obter_sessao, scope="function")],
) -> UUID:
    """412 enquanto o usuário não tiver uma API de modelos testada e ativa; devolve o id dele.

    Para as rotas que fazem pedidos aos modelos (conversas, agentes): sem provedor validado
    não há com quem falar.
    """
    from app.core.contas import tem_provedor_validado

    if not await tem_provedor_validado(sessao, usuario_id):
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            "Conecte uma API de modelos antes de fazer pedidos.",
        )
    return usuario_id
