"""Ferramenta ``mensagem_especialista`` (especificação §4; §2, ``para_agente_id``):
corrige a rota de um especialista no meio da etapa.

A mensagem vai para o correio da etapa (Redis, ver ``ambiente.py``); o worker a esvazia
com ``ler_mensagens_pendentes`` antes da próxima chamada de modelo.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.core.banco import fabrica_sessoes
from app.ferramentas.ambiente import etapa_do_usuario, guardar_mensagem
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.orquestrador.estados import FINAIS_ETAPA


class MensagemEspecialista(BaseModel):
    """Manda uma correção de rota a um especialista em andamento."""

    etapa_id: UUID
    texto: str = Field(min_length=1)


async def mensagem_especialista(args: MensagemEspecialista, contexto: ContextoFerramenta) -> str:
    """Guarda a mensagem para o especialista ler antes da próxima chamada de modelo."""
    async with fabrica_sessoes()() as sessao:
        etapa = await etapa_do_usuario(sessao, contexto, args.etapa_id)
        if etapa.status in FINAIS_ETAPA:
            raise ErroFerramenta(f"A etapa já terminou ({etapa.status.value}).")
        etapa_id = etapa.id
    await guardar_mensagem(etapa_id, args.texto)
    return "Mensagem entregue ao especialista; ele a lê antes do próximo passo."
