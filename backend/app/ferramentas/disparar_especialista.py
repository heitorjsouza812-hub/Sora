"""Ferramenta ``disparar_especialista`` (especificação §4): a Sora põe um
especialista para trabalhar numa etapa da cadeia.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.ferramentas.base import ContextoFerramenta
from app.modelos.enumeracoes import Nivel


class DispararEspecialista(BaseModel):
    """Dispara um especialista com uma tarefa."""

    papel: Literal["pesquisador", "redator", "designer", "verificador"]
    tarefa: str = Field(min_length=1)
    nivel: Nivel | None = None


async def disparar_especialista(args: DispararEspecialista, contexto: ContextoFerramenta) -> str:
    """Cria ou reaproveita a etapa e enfileira ``executar_etapa``. Devolve o ``etapa_id``."""
    raise NotImplementedError
