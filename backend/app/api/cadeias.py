"""Rotas de consulta e cancelamento de cadeias; especificação §§2 e 6."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.dependencias import usuario_atual
from app.modelos.esquemas import CadeiaSaida

roteador = APIRouter(prefix="/cadeias", tags=["cadeias"], dependencies=[Depends(usuario_atual)])


@roteador.get("/{cadeia_id}")
async def obter_cadeia(cadeia_id: UUID) -> CadeiaSaida:
    """Retorna plano, etapas, passos, modelos e custos da cadeia."""
    raise NotImplementedError


@roteador.post("/{cadeia_id}/cancelar", status_code=status.HTTP_202_ACCEPTED)
async def cancelar_cadeia(cadeia_id: UUID) -> None:
    """Solicita o cancelamento idempotente de uma cadeia."""
    raise NotImplementedError
