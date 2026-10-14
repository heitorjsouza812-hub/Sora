"""Provedor SearXNG (especificação §8.1): só para desenvolvimento local, opcional
(``docker compose --profile dev``). Nunca em produção.
"""

from __future__ import annotations

import httpx

from app.busca.provedor import ResultadoBusca, montar_resultados, pedir_json


class BuscaSearxng:
    """``ProvedorBusca`` sobre uma instância local do SearXNG (``format=json``)."""

    def __init__(self, base_url: str, *, cliente: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._cliente = cliente

    async def buscar(
        self, consulta: str, idioma: str = "pt-BR", limite: int = 5
    ) -> list[ResultadoBusca]:
        dados = await pedir_json(
            self._cliente,
            "searxng",
            "GET",
            f"{self._base_url}/search",
            params={"q": consulta, "format": "json", "language": idioma},
        )
        itens = dados.get("results", []) if isinstance(dados, dict) else []
        return montar_resultados(itens, titulo="title", url="url", trecho="content", limite=limite)
