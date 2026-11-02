"""Ferramenta ``ler_pagina`` (especificação §4 e §8.1). Delega o download seguro
(SSRF, limites, cache) e a extração a ``app.busca.ler_pagina``; nada aqui enfraquece
essas travas. A cerca ``<dado_externo>`` é posta por ``MiddlewareCerca``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.busca import ler_pagina as leitor
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.infra import obter_redis


class LerPagina(BaseModel):
    """Abre uma página da web e devolve o texto principal."""

    url: str = Field(min_length=1, max_length=2000)


async def ler_pagina(args: LerPagina, contexto: ContextoFerramenta) -> str:
    """Lê a página e devolve o texto (o worker move o que passar de 20.000 caracteres)."""
    try:
        pagina = await leitor.ler_pagina(args.url, redis=obter_redis())
    except leitor.EnderecoBloqueado as erro:
        raise ErroFerramenta(str(erro) or "Esse endereço não pode ser aberto.") from erro
    except (leitor.ErroLeitura, ValueError) as erro:
        raise ErroFerramenta(str(erro)) from erro
    cabecalho = f"Título: {pagina.titulo}\n" if pagina.titulo else ""
    return f"{cabecalho}Endereço: {pagina.url_final}\n\n{pagina.texto}"
