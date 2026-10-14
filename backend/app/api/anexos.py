"""Rotas de envio e leitura de anexos; especificação §2."""

from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, status
from fastapi.responses import FileResponse

from app.core.dependencias import usuario_atual
from app.modelos.esquemas import AnexoSaida

roteador = APIRouter(prefix="/anexos", tags=["anexos"], dependencies=[Depends(usuario_atual)])


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def enviar_anexo(arquivo: UploadFile) -> AnexoSaida:
    """Armazena um arquivo validado de até 20 MB."""
    raise NotImplementedError


@roteador.get("/{anexo_id}", response_class=FileResponse)
async def baixar_anexo(anexo_id: UUID) -> FileResponse:
    """Entrega um arquivo pertencente ao usuário autenticado."""
    raise NotImplementedError
