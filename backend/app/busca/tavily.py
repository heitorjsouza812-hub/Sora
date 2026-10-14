"""Provedor de busca Tavily (especificação §8.1, fase 1; chave da equipe em
``BUSCA_CHAVE``, só no servidor).
"""

from __future__ import annotations

from app.busca.provedor import ResultadoBusca


class BuscaTavily:
    """``ProvedorBusca`` sobre a API JSON do Tavily."""

    def __init__(self, chave: str) -> None:
        raise NotImplementedError

    async def buscar(
        self, consulta: str, idioma: str = "pt-BR", limite: int = 5
    ) -> list[ResultadoBusca]:
        raise NotImplementedError
