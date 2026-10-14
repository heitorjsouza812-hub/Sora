"""Provedor de busca Tavily (especificação §8.1, fase 1; chave da equipe em
``BUSCA_CHAVE``, só no servidor).

O Tavily devolve trechos longos da página em ``content``, o que economiza
chamadas de ``ler_pagina``.
"""

from __future__ import annotations

import httpx

from app.busca.provedor import ResultadoBusca, montar_resultados, pedir_json

URL_TAVILY = "https://api.tavily.com/search"

PAISES = {"BR": "brazil", "PT": "portugal", "US": "united states"}
"""Região (``pt-BR`` → ``BR``) → valor do parâmetro ``country`` do Tavily."""


class BuscaTavily:
    """``ProvedorBusca`` sobre a API JSON do Tavily."""

    def __init__(self, chave: str, *, cliente: httpx.AsyncClient | None = None) -> None:
        self._chave = chave
        self._cliente = cliente

    def __repr__(self) -> str:  # a chave nunca aparece em log
        return "BuscaTavily()"

    async def buscar(
        self, consulta: str, idioma: str = "pt-BR", limite: int = 5
    ) -> list[ResultadoBusca]:
        corpo: dict[str, object] = {
            "query": consulta,
            "max_results": limite,
            "search_depth": "basic",
            "topic": "general",
            "include_answer": False,
        }
        regiao = idioma.split("-", 1)[1].upper() if "-" in idioma else ""
        if regiao in PAISES:
            corpo["country"] = PAISES[regiao]
        dados = await pedir_json(
            self._cliente,
            "tavily",
            "POST",
            URL_TAVILY,
            json=corpo,
            headers={"Authorization": f"Bearer {self._chave}"},
        )
        itens = dados.get("results", []) if isinstance(dados, dict) else []
        return montar_resultados(itens, titulo="title", url="url", trecho="content", limite=limite)
