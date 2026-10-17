"""Rota da prioridade de seleção de modelos; especificação §§2 e 5."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.modelos.esquemas import PreferenciasAtualizacao
from app.modelos.tabelas import Usuario

roteador = APIRouter(
    prefix="/preferencias", tags=["preferencias"], dependencies=[Depends(usuario_atual)]
)


@roteador.patch("", status_code=status.HTTP_204_NO_CONTENT)
async def atualizar_preferencias(
    dados: PreferenciasAtualizacao,
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(obter_sessao, scope="function")],
) -> None:
    """Atualiza a prioridade entre custo, velocidade e qualidade (``usuarios.prioridade``)."""
    await sessao.execute(
        update(Usuario).where(Usuario.id == usuario_id).values(prioridade=dados.prioridade)
    )
