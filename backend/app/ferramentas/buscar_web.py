"""Ferramenta ``buscar_web`` (especificação §4 e §8.1). Usa o ``ProvedorBusca``
configurado (``app/busca``), com cache de 24 h e limites por cadeia e por dia.
O resultado entra na cerca ``<dado_externo>``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.ferramentas.base import ContextoFerramenta


class BuscarWeb(BaseModel):
    """Busca na web e devolve título, link e trecho dos melhores resultados."""

    consulta: str = Field(min_length=1, max_length=400)
    max_resultados: int = Field(default=5, ge=1, le=5)


async def buscar_web(args: BuscarWeb, contexto: ContextoFerramenta) -> str:
    """Busca, corta para os melhores resultados e devolve o texto já cercado."""
    raise NotImplementedError
