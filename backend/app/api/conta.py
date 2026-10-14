"""Rotas da conta autenticada e LGPD; especificação §8.2."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CAMINHO_COOKIE, COOKIE_RENOVACAO
from app.core import contas
from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.modelos.esquemas import ApagarContaEntrada, ContaSaida

roteador = APIRouter(tags=["conta"])


@roteador.get("/eu")
async def obter_eu(
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(obter_sessao)],
) -> ContaSaida:
    """Retorna dados mínimos da conta e do onboarding."""
    usuario, tem_provedor = await contas.dados_da_conta(sessao, usuario_id)
    return ContaSaida(
        nome=usuario.nome,
        email=usuario.email,
        prioridade=usuario.prioridade,
        tem_provedor=tem_provedor,
    )


@roteador.delete("/conta", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_conta(
    dados: ApagarContaEntrada,
    resposta: Response,
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(obter_sessao)],
) -> None:
    """Apaga os dados pertencentes ao usuário após confirmar a senha."""
    await contas.apagar_conta(sessao, usuario_id, dados.senha)
    resposta.delete_cookie(COOKIE_RENOVACAO, path=CAMINHO_COOKIE)
