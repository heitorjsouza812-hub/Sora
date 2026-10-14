"""Ferramenta ``veredito`` (especificação §4; prompt do Verificador em
``prompts/verificador.v1.md``). É também o esquema da saída do Verificador.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.ferramentas.base import ContextoFerramenta

StatusRequisito = Literal["atendido", "parcial", "contradito", "sem_evidencia"]


class RequisitoVerificado(BaseModel):
    requisito: str
    evidencia: str
    status: StatusRequisito


class Veredito(BaseModel):
    """Resultado da verificação: aprovado só se todos os requisitos estiverem atendidos."""

    aprovado: bool
    requisitos: list[RequisitoVerificado]
    motivo: str


async def veredito(args: Veredito, contexto: ContextoFerramenta) -> str:
    """Grava o veredito na etapa do Verificador e encerra o laço."""
    raise NotImplementedError
