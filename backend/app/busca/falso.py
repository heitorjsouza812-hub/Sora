"""Provedor de busca falso (especificação §8.1 e §8.5): resultados fixos, sem
rede. Usado nos testes e com o modelo falso (``SORA_MODELO_FALSO=1``).
"""

from __future__ import annotations

from app.busca.provedor import ResultadoBusca


class BuscaFalsa:
    """``ProvedorBusca`` que devolve resultados prontos."""

    def __init__(self, resultados: list[ResultadoBusca] | None = None) -> None:
        raise NotImplementedError

    async def buscar(
        self, consulta: str, idioma: str = "pt-BR", limite: int = 5
    ) -> list[ResultadoBusca]:
        raise NotImplementedError
