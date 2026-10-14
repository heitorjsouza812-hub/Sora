"""Provedor SearXNG (especificação §8.1): só para desenvolvimento local, opcional
(``docker compose --profile dev``). Nunca em produção.
"""

from __future__ import annotations

from app.busca.provedor import ResultadoBusca


class BuscaSearxng:
    """``ProvedorBusca`` sobre uma instância local do SearXNG."""

    def __init__(self, base_url: str) -> None:
        raise NotImplementedError

    async def buscar(
        self, consulta: str, idioma: str = "pt-BR", limite: int = 5
    ) -> list[ResultadoBusca]:
        raise NotImplementedError
