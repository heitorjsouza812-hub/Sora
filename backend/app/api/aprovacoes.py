"""Rotas dos cartões de aprovação; especificação §§2 e 6.1."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.dependencias import usuario_atual
from app.modelos.esquemas import DecisaoAprovacaoEntrada

roteador = APIRouter(
    prefix="/aprovacoes", tags=["aprovacoes"], dependencies=[Depends(usuario_atual)]
)


@roteador.post("/{aprovacao_id}/decidir", status_code=status.HTTP_204_NO_CONTENT)
async def decidir_aprovacao(aprovacao_id: UUID, dados: DecisaoAprovacaoEntrada) -> None:
    """Registra a decisão e retoma a etapa interrompida."""
    raise NotImplementedError
