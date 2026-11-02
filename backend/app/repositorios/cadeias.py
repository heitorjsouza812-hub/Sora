"""Leitura e cancelamento das cadeias pertencentes ao usuário."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.enumeracoes import StatusCadeia, StatusEtapa
from app.modelos.tabelas import Cadeia, Etapa, Passo

STATUS_FINAIS = frozenset({StatusCadeia.CONCLUIDA, StatusCadeia.FALHOU, StatusCadeia.CANCELADA})


async def obter(sessao: AsyncSession, usuario_id: UUID, cadeia_id: UUID) -> Cadeia | None:
    return await sessao.scalar(
        select(Cadeia).where(Cadeia.id == cadeia_id, Cadeia.usuario_id == usuario_id)
    )


async def detalhar(
    sessao: AsyncSession, usuario_id: UUID, cadeia_id: UUID
) -> tuple[Cadeia, list[Etapa], list[Passo]] | None:
    cadeia = await obter(sessao, usuario_id, cadeia_id)
    if cadeia is None:
        return None
    etapas = list(
        (
            await sessao.scalars(
                select(Etapa)
                .where(Etapa.cadeia_id == cadeia_id)
                .order_by(Etapa.ordem, Etapa.tentativa, Etapa.id)
            )
        ).all()
    )
    ids = [etapa.id for etapa in etapas]
    passos = (
        list(
            (
                await sessao.scalars(
                    select(Passo)
                    .where(Passo.etapa_id.in_(ids))
                    .order_by(Passo.iniciado_em, Passo.id)
                )
            ).all()
        )
        if ids
        else []
    )
    return cadeia, etapas, passos


async def cancelar(sessao: AsyncSession, usuario_id: UUID, cadeia_id: UUID) -> Cadeia | None:
    cadeia = await obter(sessao, usuario_id, cadeia_id)
    if cadeia is None:
        return None
    if cadeia.status in STATUS_FINAIS:
        return cadeia
    cadeia.status = StatusCadeia.CANCELADA
    await sessao.execute(
        update(Etapa)
        .where(
            Etapa.cadeia_id == cadeia_id,
            Etapa.status.not_in([StatusEtapa.CONCLUIDA, StatusEtapa.FALHOU, StatusEtapa.CANCELADA]),
        )
        .values(status=StatusEtapa.CANCELADA)
    )
    await sessao.flush()
    return cadeia
