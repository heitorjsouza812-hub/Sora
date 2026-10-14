"""Provedor de busca falso (especificação §8.1 e §8.5): resultados fixos, sem
rede. Usado nos testes e com o modelo falso (``SORA_MODELO_FALSO=1``).
"""

from __future__ import annotations

from app.busca.provedor import ResultadoBusca

RESULTADOS_PADRAO: tuple[ResultadoBusca, ...] = (
    ResultadoBusca(
        titulo="Guia de cafeterias de especialidade",
        url="https://exemplo.com.br/guia-cafeterias",
        trecho="Um panorama das cafeterias de especialidade e do que os clientes procuram.",
        origem="exemplo.com.br",
    ),
    ResultadoBusca(
        titulo="Tendências de bebidas geladas",
        url="https://exemplo.org/tendencias-bebidas-geladas",
        trecho="Café gelado, cold brew e bebidas com frutas lideram os pedidos no verão.",
        origem="exemplo.org",
    ),
    ResultadoBusca(
        titulo="Como divulgar um negócio local nas redes",
        url="https://exemplo.net/divulgar-negocio-local",
        trecho="Fotos do produto, horários fixos de postagem e respostas rápidas aos comentários.",
        origem="exemplo.net",
    ),
)
"""Domínios ``exemplo.*`` são reservados para exemplo: nunca apontam para alguém real."""


class BuscaFalsa:
    """``ProvedorBusca`` que devolve resultados prontos e guarda as consultas feitas."""

    def __init__(self, resultados: list[ResultadoBusca] | None = None) -> None:
        self.resultados = list(RESULTADOS_PADRAO if resultados is None else resultados)
        self.consultas: list[str] = []

    async def buscar(
        self, consulta: str, idioma: str = "pt-BR", limite: int = 5
    ) -> list[ResultadoBusca]:
        self.consultas.append(consulta)
        return self.resultados[:limite]
