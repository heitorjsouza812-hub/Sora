"""Ferramenta ``ver_especialista`` (especificação §4): a Sora confere o estado de
uma etapa antes de dizer que um especialista "ainda está trabalhando".
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.ferramentas.base import ContextoFerramenta


class VerEspecialista(BaseModel):
    """Mostra o estado, o progresso e a saída parcial de uma etapa."""

    etapa_id: UUID


async def ver_especialista(args: VerEspecialista, contexto: ContextoFerramenta) -> str:
    """Lê a etapa e os últimos passos dela."""
    raise NotImplementedError
