"""Provedor de busca Brave Search (especificação §8.1, alternativa ao Tavily na
fase 1; chave da equipe em ``BUSCA_CHAVE``).
"""

from __future__ import annotations

from app.busca.provedor import ResultadoBusca


class BuscaBrave:
    """``ProvedorBusca`` sobre a API do Brave Search (idioma pt-BR, região Brasil)."""

    def __init__(self, chave: str) -> None:
        raise NotImplementedError

    async def buscar(
        self, consulta: str, idioma: str = "pt-BR", limite: int = 5
    ) -> list[ResultadoBusca]:
        raise NotImplementedError
