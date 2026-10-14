"""Rotas de APIs de modelos conectadas pelo usuário; especificação §§2 e 5."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.dependencias import usuario_atual
from app.modelos.esquemas import (
    ProvedorAtualizacao,
    ProvedorConexaoSaida,
    ProvedorCriacao,
    ProvedorSaida,
)

roteador = APIRouter(
    prefix="/provedores", tags=["provedores"], dependencies=[Depends(usuario_atual)]
)


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def conectar_provedor(dados: ProvedorCriacao) -> ProvedorConexaoSaida:
    """Testa, cifra e cadastra uma API de modelos."""
    raise NotImplementedError


@roteador.get("")
async def listar_provedores() -> list[ProvedorSaida]:
    """Lista provedores sem expor suas chaves."""
    raise NotImplementedError


@roteador.patch("/{provedor_id}")
async def atualizar_provedor(provedor_id: UUID, dados: ProvedorAtualizacao) -> ProvedorSaida:
    """Troca chave ou teto mensal de um provedor."""
    raise NotImplementedError


@roteador.delete("/{provedor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_provedor(provedor_id: UUID) -> None:
    """Remove logicamente um provedor e sua chave cifrada."""
    raise NotImplementedError
