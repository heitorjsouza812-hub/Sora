"""Ferramenta ``ver_especialista`` (especificação §4): a Sora confere o estado de
uma etapa antes de dizer que um especialista "ainda está trabalhando".
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select

from app.core.banco import fabrica_sessoes
from app.ferramentas.ambiente import etapa_do_usuario
from app.ferramentas.base import ContextoFerramenta
from app.modelos.tabelas import Passo

ULTIMOS_PASSOS = 5


class VerEspecialista(BaseModel):
    """Mostra o estado, o progresso e a saída parcial de uma etapa."""

    etapa_id: UUID


async def ver_especialista(args: VerEspecialista, contexto: ContextoFerramenta) -> str:
    """Lê a etapa e os últimos passos dela."""
    async with fabrica_sessoes()() as sessao:
        etapa = await etapa_do_usuario(sessao, contexto, args.etapa_id)
        passos = (
            await sessao.scalars(
                select(Passo)
                .where(Passo.etapa_id == etapa.id)
                .order_by(Passo.iniciado_em.desc())
                .limit(ULTIMOS_PASSOS)
            )
        ).all()
        linhas = [
            f"Etapa {etapa.ordem} ({etapa.especialista}): {etapa.status.value}, "
            f"tentativa {etapa.tentativa}.",
            f"Tarefa: {etapa.titulo or etapa.tarefa}",
        ]
        if etapa.erro:
            linhas.append(f"Erro: {etapa.erro}")
        if etapa.saida:
            linhas.append(f"Saída parcial: {str(etapa.saida)[:600]}")
        if passos:
            linhas.append("Últimos passos:")
            linhas += [f"- {p.texto} ({p.status})" for p in reversed(passos)]
        else:
            linhas.append("Ainda sem passos.")
    return "\n".join(linhas)
