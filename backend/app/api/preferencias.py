"""Rota da prioridade de seleção de modelos; especificação §§2 e 5."""

from fastapi import APIRouter, Depends, status

from app.core.dependencias import usuario_atual
from app.modelos.esquemas import PreferenciasAtualizacao

roteador = APIRouter(
    prefix="/preferencias", tags=["preferencias"], dependencies=[Depends(usuario_atual)]
)


@roteador.patch("", status_code=status.HTTP_204_NO_CONTENT)
async def atualizar_preferencias(dados: PreferenciasAtualizacao) -> None:
    """Atualiza a prioridade entre custo, velocidade e qualidade."""
    raise NotImplementedError
