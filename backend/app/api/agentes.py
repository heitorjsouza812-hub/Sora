"""Rotas de agentes individuais e especialistas; especificação §2."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.dependencias import usuario_atual
from app.modelos.enumeracoes import TipoAgente
from app.modelos.esquemas import AgenteAtualizacao, AgenteCriacao, AgenteSaida

roteador = APIRouter(prefix="/agentes", tags=["agentes"], dependencies=[Depends(usuario_atual)])


@roteador.get("")
async def listar_agentes(tipo: TipoAgente | None = None) -> list[AgenteSaida]:
    """Lista agentes do usuário, opcionalmente filtrados por tipo."""
    raise NotImplementedError


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def criar_agente(dados: AgenteCriacao) -> AgenteSaida:
    """Cria um agente individual configurado ou derivado de descrição."""
    raise NotImplementedError


@roteador.post("/{agente_id}/promover")
async def promover_agente(agente_id: UUID) -> AgenteSaida:
    """Promove um especialista a agente individual."""
    raise NotImplementedError


@roteador.patch("/{agente_id}")
async def atualizar_agente(agente_id: UUID, dados: AgenteAtualizacao) -> AgenteSaida:
    """Atualiza os campos editáveis de um agente."""
    raise NotImplementedError


@roteador.delete("/{agente_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_agente(agente_id: UUID) -> None:
    """Marca um agente individual como apagado."""
    raise NotImplementedError
