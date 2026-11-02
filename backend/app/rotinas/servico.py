"""Rotinas no banco: criar, listar, pausar, apagar e escolher as que venceram.

A escolha das vencidas usa ``FOR UPDATE SKIP LOCKED`` e avança ``proxima_execucao`` na mesma
transação: dois workers (ou dois ticks) nunca pegam a mesma ocorrência.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ferramentas.base import ErroFerramenta
from app.modelos.tabelas import Agente, Rotina, RotinaExecucao
from app.rotinas.agenda import (
    Agendar,
    Plano,
    conferir_limite,
    planejar,
    proxima_depois,
)

LOTE_DO_TICK = 50


def plano_da_rotina(rotina: Rotina) -> Plano:
    return Plano(
        tipo=rotina.tipo,  # type: ignore[arg-type]
        expressao=rotina.expressao,
        proxima_execucao=rotina.proxima_execucao or datetime.now(UTC),
        fuso=rotina.fuso,
    )


async def criar(
    sessao: AsyncSession,
    *,
    usuario_id: UUID,
    agente_id: UUID,
    conversa_id: UUID | None,
    args: Agendar,
    fuso: str | None = None,
) -> Rotina:
    dono = await sessao.scalar(
        select(Agente.id).where(
            Agente.id == agente_id, Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None)
        )
    )
    if dono is None:
        raise ErroFerramenta("Agente não encontrado.")
    ativos = await sessao.scalar(
        select(func.count())
        .select_from(Rotina)
        .where(Rotina.agente_id == agente_id, Rotina.ativa.is_(True))
    )
    conferir_limite(ativos or 0)
    plano = planejar(args, fuso=fuso)
    rotina = Rotina(
        usuario_id=usuario_id,
        agente_id=agente_id,
        conversa_id=conversa_id,
        titulo=args.titulo.strip(),
        pedido=args.pedido.strip(),
        tipo=plano.tipo,
        expressao=plano.expressao,
        fuso=plano.fuso,
        proxima_execucao=plano.proxima_execucao,
        silencioso=args.silencioso,
    )
    sessao.add(rotina)
    await sessao.flush()
    return rotina


async def obter(sessao: AsyncSession, usuario_id: UUID, rotina_id: UUID) -> Rotina | None:
    return await sessao.scalar(
        select(Rotina).where(Rotina.id == rotina_id, Rotina.usuario_id == usuario_id)
    )


async def listar(
    sessao: AsyncSession, usuario_id: UUID, agente_id: UUID | None = None
) -> list[Rotina]:
    consulta = select(Rotina).where(Rotina.usuario_id == usuario_id)
    if agente_id is not None:
        consulta = consulta.where(Rotina.agente_id == agente_id)
    return list((await sessao.scalars(consulta.order_by(Rotina.criada_em))).all())


async def retomar(rotina: Rotina, agora: datetime | None = None) -> None:
    """Reativa e recalcula a próxima execução a partir de agora (rotina única vencida
    fica sem próxima)."""
    agora = agora or datetime.now(UTC)
    rotina.ativa = True
    plano = plano_da_rotina(rotina)
    if rotina.tipo == "unico":
        if rotina.proxima_execucao is None or rotina.proxima_execucao <= agora:
            rotina.proxima_execucao = None
            rotina.ativa = False
        return
    plano.proxima_execucao = agora
    rotina.proxima_execucao = proxima_depois(plano, agora)


async def ultimas_execucoes(
    sessao: AsyncSession, rotina_id: UUID, limite: int = 20
) -> list[RotinaExecucao]:
    return list(
        (
            await sessao.scalars(
                select(RotinaExecucao)
                .where(RotinaExecucao.rotina_id == rotina_id)
                .order_by(RotinaExecucao.iniciada_em.desc())
                .limit(limite)
            )
        ).all()
    )


async def pegar_vencidas(
    sessao: AsyncSession, agora: datetime | None = None
) -> list[tuple[UUID, datetime]]:
    """Rotinas vencidas -> ``[(rotina_id, ocorrencia)]``, já com a próxima execução gravada
    (ou a rotina desativada, se era única). Quem chama confirma a transação."""
    agora = agora or datetime.now(UTC)
    vencidas = (
        await sessao.scalars(
            select(Rotina)
            .where(
                Rotina.ativa.is_(True),
                Rotina.proxima_execucao.is_not(None),
                Rotina.proxima_execucao <= agora,
            )
            .order_by(Rotina.proxima_execucao)
            .limit(LOTE_DO_TICK)
            .with_for_update(skip_locked=True)
        )
    ).all()
    saida: list[tuple[UUID, datetime]] = []
    for rotina in vencidas:
        ocorrencia = rotina.proxima_execucao
        saida.append((rotina.id, ocorrencia))
        proxima = proxima_depois(plano_da_rotina(rotina), agora)
        rotina.proxima_execucao = proxima
        if proxima is None:
            rotina.ativa = False
    return saida


def resumo_da_rotina(rotina: Rotina) -> dict[str, Any]:
    return {
        "id": str(rotina.id),
        "titulo": rotina.titulo,
        "tipo": rotina.tipo,
        "expressao": rotina.expressao,
        "proxima_execucao": rotina.proxima_execucao.isoformat() if rotina.proxima_execucao else None,
        "ativa": rotina.ativa,
        "silencioso": rotina.silencioso,
    }
