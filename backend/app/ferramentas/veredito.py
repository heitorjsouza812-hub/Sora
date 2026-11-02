"""Ferramenta ``veredito`` (especificação §4; prompt do Verificador em
``prompts/verificador.v1.md``). É também o esquema da saída do Verificador.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.core.banco import fabrica_sessoes
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.modelos.tabelas import Etapa

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
    """Grava o veredito em ``etapas.saida["veredito"]`` e encerra o laço."""
    if contexto.etapa_id is None:
        raise ErroFerramenta("O veredito pertence a uma etapa do Verificador.")
    async with fabrica_sessoes()() as sessao:
        etapa = await sessao.get(Etapa, contexto.etapa_id)
        if etapa is None or etapa.agente_id not in (None, contexto.agente_id):
            raise ErroFerramenta("Etapa não encontrada.")
        etapa.saida = {"veredito": args.model_dump(mode="json")}
        await sessao.commit()
    return "Veredito aprovado." if args.aprovado else f"Veredito reprovado: {args.motivo}"
