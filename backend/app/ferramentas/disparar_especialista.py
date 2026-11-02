"""Ferramenta ``disparar_especialista`` (especificação §4): a Sora põe um
especialista para trabalhar numa etapa da cadeia.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.banco import fabrica_sessoes
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.modelos.enumeracoes import Nivel
from app.modelos.tabelas import Cadeia, Etapa
from app.orquestrador.estados import FINAIS_ETAPA


class DispararEspecialista(BaseModel):
    """Dispara um especialista com uma tarefa."""

    papel: Literal["pesquisador", "redator", "designer", "verificador"]
    tarefa: str = Field(min_length=1)
    nivel: Nivel | None = None


async def disparar_especialista(args: DispararEspecialista, contexto: ContextoFerramenta) -> str:
    """Cria ou reaproveita a etapa e enfileira ``executar_etapa``. Devolve o ``etapa_id``."""
    from workers.fila import enfileirar

    if contexto.cadeia_id is None:
        raise ErroFerramenta("Não há cadeia ativa para disparar um especialista.")
    async with fabrica_sessoes()() as sessao:
        cadeia = await sessao.get(Cadeia, contexto.cadeia_id)
        if cadeia is None or cadeia.usuario_id != contexto.usuario_id:
            raise ErroFerramenta("Cadeia não encontrada.")
        existente = await sessao.scalar(
            select(Etapa).where(
                Etapa.cadeia_id == cadeia.id,
                Etapa.especialista == args.papel,
                Etapa.tarefa == args.tarefa,
                Etapa.status.notin_(FINAIS_ETAPA),
            )
        )
        if existente is not None:
            return str(existente.id)
        ordem = (
            await sessao.scalar(
                select(func.coalesce(func.max(Etapa.ordem), 0)).where(Etapa.cadeia_id == cadeia.id)
            )
        ) + 1
        etapa = Etapa(
            cadeia_id=cadeia.id,
            ordem=ordem,
            especialista=args.papel,
            titulo=args.tarefa[:80],
            nivel=(args.nivel or Nivel.N2).value,
            tarefa=args.tarefa,
        )
        sessao.add(etapa)
        await sessao.commit()
        etapa_id = str(etapa.id)
    await enfileirar("executar_etapa", etapa_id=etapa_id)
    return etapa_id
