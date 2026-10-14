"""Dependências compartilhadas pelas rotas protegidas; especificação §§2 e 8.2."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

esquema_bearer = HTTPBearer(
    scheme_name="BearerAuth",
    bearerFormat="JWT",
    description="Token de acesso emitido por /v1/auth/entrar ou /v1/auth/renovar.",
)


async def usuario_atual(
    credenciais: Annotated[HTTPAuthorizationCredentials, Depends(esquema_bearer)],
) -> UUID:
    """Valida o JWT de `Authorization: Bearer` e devolve o id do usuário."""
    raise NotImplementedError
