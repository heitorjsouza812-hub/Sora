"""Ferramenta ``parar_especialista`` (especificação §4): a Sora interrompe uma etapa."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.ferramentas.base import ContextoFerramenta


class PararEspecialista(BaseModel):
    """Para a etapa de um especialista."""

    etapa_id: UUID


async def parar_especialista(args: PararEspecialista, contexto: ContextoFerramenta) -> str:
    """Marca a etapa como cancelada e sinaliza o worker que a executa."""
    raise NotImplementedError
