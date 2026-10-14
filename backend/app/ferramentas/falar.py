"""Ferramenta ``falar`` (especificação §4): a única forma de a Sora e dos agentes
individuais mandarem texto ao usuário. Gera ``mensagem.inicio/delta/fim``.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.ferramentas.base import ContextoFerramenta


class Falar(BaseModel):
    """Manda uma mensagem ao usuário. Só o que passa por aqui chega a ele."""

    texto: str = Field(min_length=1)
    anexos: list[UUID] | None = None
    responde_a: UUID | None = None


async def falar(args: Falar, contexto: ContextoFerramenta) -> str:
    """Grava a mensagem visível e emite os eventos de mensagem."""
    raise NotImplementedError
