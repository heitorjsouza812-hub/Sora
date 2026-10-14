"""Rotas do catálogo de modelos disponíveis; especificação §§2 e 5."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.dependencias import usuario_atual
from app.modelos.esquemas import ModeloAtualizacao, ModeloSaida

roteador = APIRouter(prefix="/modelos", tags=["modelos"], dependencies=[Depends(usuario_atual)])


@roteador.get("")
async def listar_modelos() -> list[ModeloSaida]:
    """Lista modelos com nível, capacidades e preço."""
    raise NotImplementedError


@roteador.patch("/{modelo_id}")
async def atualizar_modelo(modelo_id: UUID, dados: ModeloAtualizacao) -> ModeloSaida:
    """Atualiza nível ou ativação definida pelo usuário."""
    raise NotImplementedError
