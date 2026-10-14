"""Rota de medição de tokens e custo; especificação §§2 e 5."""

from datetime import date

from fastapi import APIRouter, Depends

from app.core.dependencias import usuario_atual
from app.modelos.esquemas import UsoSaida

roteador = APIRouter(prefix="/uso", tags=["uso"], dependencies=[Depends(usuario_atual)])


@roteador.get("")
async def obter_uso(de: date | None = None, ate: date | None = None) -> UsoSaida:
    """Agrega tokens e custos por dia, papel e provedor."""
    raise NotImplementedError
