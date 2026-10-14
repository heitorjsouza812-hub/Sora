"""Rotas de entregas e versões da revisão; especificação §2."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.dependencias import usuario_atual
from app.modelos.esquemas import EntregasListaSaida

roteador = APIRouter(tags=["entregas"], dependencies=[Depends(usuario_atual)])


@roteador.get("/conversas/{conversa_id}/entregas")
async def listar_entregas(conversa_id: UUID, versao: int | None = None) -> EntregasListaSaida:
    """Lista entregas de uma versão e todas as versões disponíveis."""
    raise NotImplementedError
