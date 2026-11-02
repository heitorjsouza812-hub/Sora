"""Rota de medição de tokens e custo; especificação §§2 e 5."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.modelos.esquemas import UsoItem, UsoSaida
from app.modelos.tabelas import ChamadaModelo, Provedor

roteador = APIRouter(prefix="/uso", tags=["uso"], dependencies=[Depends(usuario_atual)])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
Usuario = Annotated[UUID, Depends(usuario_atual)]
JANELA_PADRAO_DIAS = 30
JANELA_MAXIMA_DIAS = 366


@roteador.get("")
async def obter_uso(
    usuario_id: Usuario, sessao: Sessao, de: date | None = None, ate: date | None = None
) -> UsoSaida:
    """Agrega tokens e custos por dia (UTC), papel e provedor; ``ate`` é inclusivo."""
    hoje = datetime.now(UTC).date()
    fim = ate or hoje
    inicio = de or fim - timedelta(days=JANELA_PADRAO_DIAS - 1)
    if inicio > fim:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "'de' vem depois de 'ate'.")
    if (fim - inicio).days >= JANELA_MAXIMA_DIAS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Período máximo: 1 ano.")
    dia = cast(func.timezone("UTC", ChamadaModelo.criado_em), Date)
    consulta = (
        select(
            dia.label("dia"),
            ChamadaModelo.papel,
            Provedor.tipo,
            func.coalesce(func.sum(ChamadaModelo.tokens_entrada), 0),
            func.coalesce(func.sum(ChamadaModelo.tokens_saida), 0),
            func.coalesce(func.sum(ChamadaModelo.custo_usd), 0),
        )
        .select_from(ChamadaModelo)
        .outerjoin(Provedor, Provedor.id == ChamadaModelo.provedor_id)
        .where(
            ChamadaModelo.usuario_id == usuario_id,
            ChamadaModelo.criado_em >= datetime.combine(inicio, time.min, tzinfo=UTC),
            ChamadaModelo.criado_em
            < datetime.combine(fim + timedelta(days=1), time.min, tzinfo=UTC),
        )
        .group_by(dia, ChamadaModelo.papel, Provedor.tipo)
        .order_by(dia, ChamadaModelo.papel)
    )
    itens = [
        UsoItem(
            data=datetime.combine(d, time.min, tzinfo=UTC),
            papel=papel,
            provedor=tipo.value if tipo is not None else None,
            tokens_entrada=int(entrada),
            tokens_saida=int(saida),
            custo_usd=float(custo),
        )
        for d, papel, tipo, entrada, saida, custo in (await sessao.execute(consulta)).all()
    ]
    return UsoSaida(itens=itens, custo_total_usd=round(sum(i.custo_usd for i in itens), 6))
