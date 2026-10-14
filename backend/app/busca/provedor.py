"""Interface comum dos provedores de busca (especificação §8.1).

``busca.provedor = "tavily" | "brave" | "searxng" | "falso"``. Cache de 24 h
por consulta no Redis; limites de 20 buscas por cadeia e 300 por usuário por
dia.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

NomeProvedor = Literal["tavily", "brave", "searxng", "falso"]

LIMITE_POR_CADEIA = 20
LIMITE_POR_USUARIO_DIA = 300
CACHE_SEGUNDOS = 24 * 60 * 60


class ResultadoBusca(BaseModel):
    titulo: str
    url: str
    trecho: str
    origem: str


class ProvedorBusca(Protocol):
    async def buscar(
        self, consulta: str, idioma: str = "pt-BR", limite: int = 5
    ) -> list[ResultadoBusca]: ...


class ErroBusca(Exception):
    """Falha do provedor (inclui o limite do mês da chave da equipe)."""


def obter_provedor(nome: NomeProvedor) -> ProvedorBusca:
    """Devolve o provedor configurado."""
    raise NotImplementedError


async def buscar_com_cache(
    provedor: ProvedorBusca, consulta: str, idioma: str = "pt-BR", limite: int = 5
) -> list[ResultadoBusca]:
    """Busca passando pelo cache do Redis (24 h por consulta)."""
    raise NotImplementedError
