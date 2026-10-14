"""Ferramenta ``criar_agente`` (especificação §4): a Sora propõe um agente
individual. Sempre pede aprovação por cartão fixo (sem modelo revisor), com a
interrupção do LangGraph (§6.1). Respeita o limite de 5 agentes individuais.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.ferramentas.base import ContextoFerramenta


class CriarAgente(BaseModel):
    """Propõe criar um agente individual; o usuário aprova no cartão."""

    nome: str = Field(min_length=1, max_length=40)
    papel: str = Field(min_length=1)


async def criar_agente(args: CriarAgente, contexto: ContextoFerramenta) -> str:
    """Cria o cartão de aprovação, interrompe e, se aprovado, cria o agente."""
    raise NotImplementedError
