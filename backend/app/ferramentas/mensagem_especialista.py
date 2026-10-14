"""Ferramenta ``mensagem_especialista`` (especificação §4; §2, ``para_agente_id``):
corrige a rota de um especialista no meio da etapa.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.ferramentas.base import ContextoFerramenta


class MensagemEspecialista(BaseModel):
    """Manda uma correção de rota a um especialista em andamento."""

    etapa_id: UUID
    texto: str = Field(min_length=1)


async def mensagem_especialista(args: MensagemEspecialista, contexto: ContextoFerramenta) -> str:
    """Guarda a mensagem para o especialista ler antes da próxima chamada de modelo."""
    raise NotImplementedError
