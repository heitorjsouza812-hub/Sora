"""Provedor DuckDuckGo HTML: busca sem chave nenhuma.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``adapters/src/keyless-http-web.ts``
(``parseDuckDuckGoResults``, ``unwrapDuckDuckGoUrl``). No Rakazo é o padrão, para o núcleo
rodar sem fornecedor pago. Na Sora ele entra como opção de **desenvolvimento** (igual ao
SearXNG): a página HTML do DuckDuckGo não é uma API e limita quem faz muitas buscas, então
produção continua com Tavily ou Brave (especificação §8.1).
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx

from app.busca.provedor import ErroBusca, ResultadoBusca, dominio

ENDERECO = "https://html.duckduckgo.com/html/"
AGENTE_USUARIO = "SoraBot/0.1 (+https://github.com/heitorjsouza812-hub/Sora)"
PRAZO_SEGUNDOS = 15
_REGIOES = {"pt-BR": "br-pt", "en": "us-en", "es": "es-es"}


def desembrulhar(href: str) -> str:
    """``//duckduckgo.com/l/?uddg=https%3A…`` → o link de verdade."""
    absoluto = urljoin(ENDERECO, href)
    alvo = parse_qs(urlsplit(absoluto).query).get("uddg")
    return alvo[0] if alvo else absoluto


class _Leitor(HTMLParser):
    """Lê os blocos ``.result`` (título em ``a.result__a``, trecho em ``.result__snippet``)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.itens: list[dict[str, str]] = []
        self._atual: dict[str, str] | None = None
        self._campo: str | None = None
        self._profundidade = 0

    @staticmethod
    def _classes(atributos: list[tuple[str, str | None]]) -> set[str]:
        return set((dict(atributos).get("class") or "").split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        if "result" in classes and tag == "div":
            self._atual = {"titulo": "", "url": "", "trecho": ""}
            self.itens.append(self._atual)
        if self._atual is None:
            return
        if tag == "a" and "result__a" in classes:
            self._atual["url"] = desembrulhar(dict(attrs).get("href") or "")
            self._campo, self._profundidade = "titulo", 1
        elif "result__snippet" in classes:
            self._campo, self._profundidade = "trecho", 1
        elif self._campo:
            self._profundidade += 1

    def handle_endtag(self, tag: str) -> None:
        if self._campo:
            self._profundidade -= 1
            if self._profundidade <= 0:
                self._campo = None

    def handle_data(self, data: str) -> None:
        if self._atual is not None and self._campo:
            self._atual[self._campo] += data


def ler_resultados(html: str, limite: int) -> list[ResultadoBusca]:
    leitor = _Leitor()
    leitor.feed(html)
    resultados: list[ResultadoBusca] = []
    for item in leitor.itens:
        url = item["url"]
        if not url.startswith(("http://", "https://")) or dominio(url).endswith("duckduckgo.com"):
            continue
        titulo = " ".join(item["titulo"].split())
        if not titulo:
            continue
        resultados.append(
            ResultadoBusca(
                titulo=titulo, url=url, trecho=" ".join(item["trecho"].split()), origem=dominio(url)
            )
        )
        if len(resultados) == limite:
            break
    return resultados


class BuscaDuckDuckGo:
    """``ProvedorBusca`` sobre a página HTML do DuckDuckGo."""

    def __init__(self, *, cliente: httpx.AsyncClient | None = None) -> None:
        self._cliente = cliente

    async def buscar(
        self, consulta: str, idioma: str = "pt-BR", limite: int = 5
    ) -> list[ResultadoBusca]:
        proprio = self._cliente is None
        cliente = self._cliente or httpx.AsyncClient(timeout=PRAZO_SEGUNDOS, trust_env=False)
        try:
            resposta = await cliente.post(
                ENDERECO,
                data={"q": consulta, "kl": _REGIOES.get(idioma, "wt-wt")},
                headers={"User-Agent": AGENTE_USUARIO},
            )
        except httpx.TimeoutException as erro:
            raise ErroBusca("A busca (duckduckgo) demorou demais.") from erro
        except httpx.HTTPError as erro:
            raise ErroBusca("Não consegui falar com a busca (duckduckgo).") from erro
        finally:
            if proprio:
                await cliente.aclose()
        if resposta.status_code in (202, 403, 429):
            raise ErroBusca("A busca (duckduckgo) limitou os pedidos. Siga com o que já tem.")
        if resposta.status_code >= 400:
            raise ErroBusca(f"A busca (duckduckgo) respondeu {resposta.status_code}.")
        return ler_resultados(resposta.text, limite)
