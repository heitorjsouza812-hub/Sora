"""Job de prazo das aprovações (especificação §6, ``expirar_aprovacao`` e
"Aprovação no meio da etapa": prazo de 10 minutos).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.eventos.streams import publicar_evento
from app.eventos.tipos import AprovacaoResolvida
from app.modelos.enumeracoes import DecisaoAprovacao, StatusAprovacao
from app.modelos.tabelas import Aprovacao, Cadeia, Conversa, Etapa
from workers.fila import enfileirar

PRAZO_APROVACAO_MINUTOS = 10


async def expirar_aprovacao(ctx: dict[str, Any], aprovacao_id: str) -> None:
    """Marca a aprovação como ``expirada`` (se ainda pendente), emite
    ``aprovacao.resolvida`` e retoma a etapa (ou a conversa) com "negado". Agendado para
    ``expira_em``; sem efeito se o usuário já decidiu."""
    async with ctx["sessoes"]() as sessao:
        aprovacao = await sessao.scalar(
            select(Aprovacao).where(Aprovacao.id == UUID(aprovacao_id)).with_for_update()
        )
        agora = datetime.now(UTC)
        if (
            aprovacao is None
            or aprovacao.status != StatusAprovacao.PENDENTE
            or aprovacao.expira_em > agora
        ):
            return
        aprovacao.status = StatusAprovacao.EXPIRADA
        aprovacao.decidida_em = agora
        conversa_id: UUID | None = None
        if aprovacao.etapa_id is not None:
            conversa_id = await sessao.scalar(
                select(Cadeia.conversa_id)
                .join(Etapa, Etapa.cadeia_id == Cadeia.id)
                .where(Etapa.id == aprovacao.etapa_id)
            )
        elif isinstance(aprovacao.acao, dict):
            try:
                candidata = UUID(str(aprovacao.acao.get("conversa_id")))
            except ValueError:
                candidata = None
            if candidata is not None:
                conversa_id = await sessao.scalar(
                    select(Conversa.id).where(
                        Conversa.id == candidata, Conversa.usuario_id == aprovacao.usuario_id
                    )
                )
        etapa_id, usuario_id, id_aprovacao = aprovacao.etapa_id, aprovacao.usuario_id, aprovacao.id
        await sessao.commit()
    resposta = {"aprovacao_id": str(id_aprovacao), "decisao": DecisaoAprovacao.NEGAR.value}
    if conversa_id is not None:
        await publicar_evento(
            ctx["redis_eventos"],
            AprovacaoResolvida(aprovacao_id=id_aprovacao, status=StatusAprovacao.EXPIRADA),
            conversa_id,
            usuario_id,
        )
    if etapa_id is not None:
        await enfileirar(
            "executar_etapa",
            id_job=f"aprovacao:{id_aprovacao}",
            etapa_id=str(etapa_id),
            resposta=resposta,
        )
    elif conversa_id is not None:
        await enfileirar(
            "retomar_conversa",
            id_job=f"aprovacao:{id_aprovacao}",
            conversa_id=str(conversa_id),
            resposta=resposta,
        )
