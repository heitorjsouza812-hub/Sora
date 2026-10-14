"""Ferramenta ``ler_pagina`` (especificação §4 e §8.1). Delega o download seguro
e a extração a ``app.busca.ler_pagina``; o resultado entra na cerca.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.ferramentas.base import ContextoFerramenta


class LerPagina(BaseModel):
    """Abre uma página da web e devolve o texto principal."""

    url: str = Field(min_length=1, max_length=2000)


async def ler_pagina(args: LerPagina, contexto: ContextoFerramenta) -> str:
    """Lê a página e devolve o texto cercado (ou o caminho do arquivo, se for grande)."""
    raise NotImplementedError
