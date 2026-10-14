"""Ferramenta ``entregar`` (especificação §4): fim da etapa de um especialista.
Vira uma linha em ``entregas`` (``app.orquestrador.entregas``) e o evento
``entrega``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ferramentas.base import ContextoFerramenta


class Entregar(BaseModel):
    """Entrega o resultado da etapa para a Sora e para a Revisão."""

    tipo: Literal["texto", "links", "imagem", "calendario", "arquivo"]
    titulo: str = Field(max_length=40, description='Uma palavra: "Pesquisa", "Peças", "Calendário"')
    resumo: str = Field(max_length=80, description='Curto: "4 referências", "3 peças", "12 posts"')
    conteudo: dict[str, Any] | list[Any] | str
    fontes: list[str] = Field(default_factory=list)
    pendencias: list[str] = Field(default_factory=list)


async def entregar(args: Entregar, contexto: ContextoFerramenta) -> str:
    """Grava a entrega e encerra o laço do agente."""
    raise NotImplementedError
