"""Dependências compartilhadas pelas rotas protegidas; especificação §§2 e 8.2."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from app.core.seguranca import ErroToken, decodificar_token_acesso

esquema_bearer = HTTPBearer(
    scheme_name="BearerAuth",
    bearerFormat="JWT",
    description="Token de acesso emitido por /v1/auth/entrar ou /v1/auth/renovar.",
)


async def usuario_atual(
    credenciais: Annotated[HTTPAuthorizationCredentials, Depends(esquema_bearer)],
) -> UUID:
    """Valida o JWT de `Authorization: Bearer` e devolve o id do usuário."""
    try:
        carga = decodificar_token_acesso(credenciais.credentials)
        return UUID(carga["sub"])
    except (ErroToken, KeyError, ValueError) as erro:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token de acesso inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from erro


def obter_redis(requisicao: Request) -> Redis:
    """Cliente Redis criado no lifespan da aplicação (`app.state.redis`)."""
    return requisicao.app.state.redis
