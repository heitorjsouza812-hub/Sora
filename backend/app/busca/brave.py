"""Provedor de busca Brave Search (especificação §8.1, alternativa ao Tavily na
fase 1; chave da equipe em ``BUSCA_CHAVE``).
"""

from __future__ import annotations

import html
import re

import httpx

from app.busca.provedor import ResultadoBusca, montar_resultados, pedir_json

URL_BRAVE = "https://api.search.brave.com/res/v1/web/search"
MAX_POR_PEDIDO = 20

_TAGS = re.compile(r"<[^>]+>")


def limpar_trecho(texto: str) -> str:
    """O Brave marca os termos com ``<strong>``; tira as tags e as entidades."""
    return html.unescape(_TAGS.sub("", texto)).strip()


class BuscaBrave:
    """``ProvedorBusca`` sobre a API do Brave Search (idioma pt-BR, região Brasil)."""

    def __init__(self, chave: str, *, cliente: httpx.AsyncClient | None = None) -> None:
        self._chave = chave
        self._cliente = cliente

    def __repr__(self) -> str:  # a chave nunca aparece em log
        return "BuscaBrave()"

    async def buscar(
        self, consulta: str, idioma: str = "pt-BR", limite: int = 5
    ) -> list[ResultadoBusca]:
        lingua, _, regiao = idioma.partition("-")
        parametros: dict[str, str | int] = {
            "q": consulta,
            "count": min(limite, MAX_POR_PEDIDO),
            "search_lang": idioma.lower() if lingua == "pt" else lingua.lower(),
            "ui_lang": idioma,
            "safesearch": "moderate",
        }
        if regiao:
            parametros["country"] = regiao.upper()
        dados = await pedir_json(
            self._cliente,
            "brave",
            "GET",
            URL_BRAVE,
            params=parametros,
            headers={"X-Subscription-Token": self._chave, "Accept": "application/json"},
        )
        web = dados.get("web", {}) if isinstance(dados, dict) else {}
        itens = web.get("results", []) if isinstance(web, dict) else []
        resultados = montar_resultados(
            itens, titulo="title", url="url", trecho="description", limite=limite
        )
        return [
            r.model_copy(
                update={"titulo": limpar_trecho(r.titulo), "trecho": limpar_trecho(r.trecho)}
            )
            for r in resultados
        ]
