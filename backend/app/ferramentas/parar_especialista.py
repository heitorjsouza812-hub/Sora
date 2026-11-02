"""Ferramenta ``parar_especialista`` (especificação §4): a Sora interrompe uma etapa."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from app.core.banco import fabrica_sessoes
from app.eventos.tipos import EtapaAtualizada
from app.ferramentas.ambiente import emitir, etapa_do_usuario
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.modelos.enumeracoes import StatusEtapa
from app.orquestrador.estados import FINAIS_ETAPA, pode_mudar_etapa


class PararEspecialista(BaseModel):
    """Para a etapa de um especialista."""

    etapa_id: UUID


async def parar_especialista(args: PararEspecialista, contexto: ContextoFerramenta) -> str:
    """Marca a etapa como cancelada e sinaliza o worker que a executa.

    O sinal é o próprio ``etapas.status``: o worker confere antes de cada passo e o
    middleware de cancelamento encerra a etapa cancelada.
    """
    async with fabrica_sessoes()() as sessao:
        etapa = await etapa_do_usuario(sessao, contexto, args.etapa_id)
        if etapa.status in FINAIS_ETAPA:
            return f"A etapa já estava {etapa.status.value}."
        if not pode_mudar_etapa(etapa.status, StatusEtapa.CANCELADA):
            raise ErroFerramenta(f"Não dá para parar uma etapa {etapa.status.value}.")
        etapa.status = StatusEtapa.CANCELADA
        etapa.concluida_em = datetime.now(UTC)
        await sessao.commit()
        evento = EtapaAtualizada(
            etapa_id=etapa.id,
            status=etapa.status,
            progresso=0,
            modelo=etapa.modelo,
            tokens=etapa.tokens,
            custo_usd=float(etapa.custo_usd),
        )
    await emitir(contexto, evento)
    return "Etapa cancelada."
