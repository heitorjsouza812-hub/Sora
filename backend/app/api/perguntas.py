"""Rotas de resposta aos cartões de pergunta; especificação §2."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.dependencias import usuario_atual
from app.modelos.esquemas import RespostaPerguntaEntrada

roteador = APIRouter(prefix="/perguntas", tags=["perguntas"], dependencies=[Depends(usuario_atual)])


@roteador.post("/{pergunta_id}/responder", status_code=status.HTTP_204_NO_CONTENT)
async def responder_pergunta(pergunta_id: UUID, dados: RespostaPerguntaEntrada) -> None:
    """Registra a resposta e retoma a etapa interrompida."""
    raise NotImplementedError
