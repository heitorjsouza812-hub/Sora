"""Ferramenta ``buscar_web`` (especificação §4 e §8.1). Usa o ``ProvedorBusca``
configurado (``app/busca``), com cache de 24 h e limites por cadeia e por dia.

O resultado volta como texto puro: a cerca ``<dado_externo>`` é posta por
``MiddlewareCerca`` (``app/agentes/middleware/cerca.py``), uma vez só.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.busca.provedor import ErroBusca, ResultadoBusca, buscar, obter_provedor
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.infra import obter_redis


class BuscarWeb(BaseModel):
    """Busca na web e devolve título, link e trecho dos melhores resultados."""

    consulta: str = Field(min_length=1, max_length=400)
    max_resultados: int = Field(default=5, ge=1, le=5)


def formatar_resultados(resultados: list[ResultadoBusca]) -> str:
    if not resultados:
        return "Nenhum resultado encontrado."
    blocos = [
        f"{i}. {r.titulo}\n   {r.url} ({r.origem})\n   {r.trecho}"
        for i, r in enumerate(resultados, start=1)
    ]
    return "\n\n".join(blocos)


async def buscar_web(args: BuscarWeb, contexto: ContextoFerramenta) -> str:
    """Busca, corta para os melhores resultados e devolve o texto."""
    from app.core.config import obter_configuracao

    config = obter_configuracao()
    chave = config.busca_chave.get_secret_value() if config.busca_chave else None
    try:
        provedor = obter_provedor(config.busca_provedor, chave=chave, ambiente=config.ambiente)
        resultados = await buscar(
            obter_redis(),
            provedor,
            config.busca_provedor,
            args.consulta,
            usuario_id=contexto.usuario_id,
            cadeia_id=contexto.cadeia_id,
            limite=args.max_resultados,
        )
    except ErroBusca as erro:
        raise ErroFerramenta(str(erro)) from erro
    return formatar_resultados(resultados[: args.max_resultados])
