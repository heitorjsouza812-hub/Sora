"""Rotas da conta autenticada e LGPD; especificação §8.2."""

from fastapi import APIRouter, Depends, status

from app.core.dependencias import usuario_atual
from app.modelos.esquemas import ApagarContaEntrada, ContaSaida

roteador = APIRouter(tags=["conta"], dependencies=[Depends(usuario_atual)])


@roteador.get("/eu")
async def obter_eu() -> ContaSaida:
    """Retorna dados mínimos da conta e do onboarding."""
    raise NotImplementedError


@roteador.delete("/conta", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_conta(dados: ApagarContaEntrada) -> None:
    """Apaga os dados pertencentes ao usuário após confirmar a senha."""
    raise NotImplementedError
