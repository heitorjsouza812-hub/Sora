"""Lista unificada dos cartões que aguardam decisão do usuário."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.atencao import PedidoAtencao, listar_atencao
from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual

roteador = APIRouter(prefix="/atencao", tags=["atencao"], dependencies=[Depends(usuario_atual)])
Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
Usuario = Annotated[UUID, Depends(usuario_atual)]


@roteador.get("")
async def listar_pedidos(usuario_id: Usuario, sessao: Sessao) -> list[PedidoAtencao]:
    return await listar_atencao(sessao, usuario_id)
