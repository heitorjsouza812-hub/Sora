"""Reconciliador de etapas travadas (especificação §6, "Retomada").

Se o processo do worker morre no meio de uma etapa, a linha fica ``executando`` para sempre:
o ARQ reentrega o job, mas ``pegar_etapa`` só pega etapas ``pendente``. Este job roda a cada
minuto (``cron_jobs`` do ``WorkerSettings``), pergunta a ``acao_para`` o que fazer e devolve a
etapa para a fila uma vez; se acontecer de novo, a etapa (e a cadeia) falham com evento.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from app.eventos.tipos import CadeiaAtualizada, EtapaAtualizada
from app.modelos.enumeracoes import StatusAprovacao, StatusCadeia, StatusEtapa
from app.modelos.tabelas import Aprovacao, Cadeia, Etapa
from app.orquestrador.travados import MAX_RETOMADAS, Acao, EtapaParada, acao_para
from workers.fila import enfileirar

PRAZO_CONTADOR_S = 7 * 24 * 60 * 60

BATIMENTO_TTL_S = 15
"""O worker renova a chave de batimento a cada ``BATIMENTO_INTERVALO_S`` enquanto a etapa roda;
sem renovar por ``BATIMENTO_TTL_S``, o processo morreu."""
BATIMENTO_INTERVALO_S = 5
CARENCIA_S = 30
"""Tempo mínimo desde o início da etapa antes de dar o worker por morto pela falta de batimento."""


def _chave_batimento(etapa_id: UUID) -> str:
    return f"batimento:{etapa_id}"


@asynccontextmanager
async def batimento(redis: Any, etapa_id: UUID) -> AsyncIterator[None]:
    """Mantém o sinal de vida da etapa enquanto o bloco roda (etapa longa saudável nunca é
    confundida com worker morto)."""

    async def pulsar() -> None:
        while True:
            try:
                await redis.set(_chave_batimento(etapa_id), "1", ex=BATIMENTO_TTL_S)
            except Exception:
                pass  # um tropeço do Redis não derruba a etapa; o próximo pulso tenta de novo
            await asyncio.sleep(BATIMENTO_INTERVALO_S)

    tarefa = asyncio.create_task(pulsar())
    try:
        await asyncio.sleep(0)  # o primeiro pulso sai antes de a etapa começar a trabalhar
        yield
    finally:
        tarefa.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await tarefa
        with suppress(Exception):
            await redis.delete(_chave_batimento(etapa_id))


def _chave_retomadas(etapa_id: UUID) -> str:
    return f"retomadas:{etapa_id}"


async def reconciliar_travados(ctx: dict[str, Any]) -> dict[str, int]:
    """Devolve quantas etapas foram retomadas e quantas falharam."""
    redis = ctx["redis_eventos"]
    agora = datetime.now(UTC)
    retomadas = falhas = 0
    async with ctx["sessoes"]() as sessao:
        candidatas = (
            await sessao.execute(
                select(Etapa.id, Etapa.iniciada_em).where(
                    Etapa.status == StatusEtapa.EXECUTANDO, Etapa.iniciada_em.is_not(None)
                )
            )
        ).all()
    for etapa_id, iniciada_em in candidatas:
        ja = int(await redis.get(_chave_retomadas(etapa_id)) or 0)
        morto = (
            not await redis.exists(_chave_batimento(etapa_id))
            and (agora - iniciada_em).total_seconds() >= CARENCIA_S
        )
        if morto:
            # sem batimento: o processo do worker morreu; não precisa esperar o prazo da etapa
            acao = Acao.RETOMAR if ja < MAX_RETOMADAS else Acao.FALHAR
        else:
            acao = acao_para(
                EtapaParada(str(etapa_id), "executando", iniciada_em, retomadas=ja), agora
            )
        if acao == Acao.RETOMAR and await _retomar(ctx, etapa_id):
            retomadas += 1
        elif acao == Acao.FALHAR and await _falhar(ctx, etapa_id):
            falhas += 1
    # Rede de segurança: cartão vencido cujo job agendado se perdeu.
    from workers.aprovacoes import expirar_aprovacao

    async with ctx["sessoes"]() as sessao:
        vencidas = (
            await sessao.scalars(
                select(Aprovacao.id).where(
                    Aprovacao.status == StatusAprovacao.PENDENTE, Aprovacao.expira_em <= agora
                )
            )
        ).all()
    for aprovacao_id in vencidas:
        await expirar_aprovacao(ctx, str(aprovacao_id))
    return {"retomadas": retomadas, "falhas": falhas}


async def _publicar(ctx: dict[str, Any], cadeia: Cadeia, evento: Any) -> None:
    from app.eventos.streams import publicar_evento

    await publicar_evento(ctx["redis_eventos"], evento, cadeia.conversa_id, cadeia.usuario_id)


def _evento_etapa(etapa: Etapa) -> EtapaAtualizada:
    return EtapaAtualizada(
        etapa_id=etapa.id,
        status=etapa.status,
        progresso=0 if etapa.status == StatusEtapa.PENDENTE else 100,
        modelo=etapa.modelo or "",
        tokens=etapa.tokens,
        custo_usd=float(etapa.custo_usd or 0),
    )


def _evento_cadeia(cadeia: Cadeia) -> CadeiaAtualizada:
    return CadeiaAtualizada(
        cadeia_id=cadeia.id,
        status=cadeia.status,
        tokens_usados=cadeia.tokens_usados,
        custo_usd=float(cadeia.custo_usd or 0),
    )


async def _retomar(ctx: dict[str, Any], etapa_id: UUID) -> bool:
    """Etapa ``executando`` -> ``pendente`` e de volta para a fila (uma vez só vence)."""
    async with ctx["sessoes"]() as sessao:
        voltou = await sessao.scalar(
            update(Etapa)
            .where(Etapa.id == etapa_id, Etapa.status == StatusEtapa.EXECUTANDO)
            .values(status=StatusEtapa.PENDENTE, iniciada_em=None)
            .returning(Etapa.id)
        )
        if voltou is None:
            await sessao.rollback()
            return False
        etapa = await sessao.get(Etapa, etapa_id)
        cadeia = await sessao.get(Cadeia, etapa.cadeia_id, with_for_update=True)
        verificador = etapa.especialista == "verificador"
        if verificador and cadeia.status == StatusCadeia.VERIFICANDO:
            cadeia.status = StatusCadeia.EXECUTANDO
        await sessao.commit()
        await ctx["redis_eventos"].incr(_chave_retomadas(etapa_id))
        await ctx["redis_eventos"].expire(_chave_retomadas(etapa_id), PRAZO_CONTADOR_S)
        await _publicar(ctx, cadeia, _evento_etapa(etapa))
        if verificador:
            await _publicar(ctx, cadeia, _evento_cadeia(cadeia))
            await enfileirar("verificar_cadeia", cadeia_id=str(cadeia.id))
        else:
            await enfileirar("executar_etapa", etapa_id=str(etapa_id))
    return True


async def _falhar(ctx: dict[str, Any], etapa_id: UUID) -> bool:
    """Segunda queda: etapa ``falhou`` com o motivo; a cadeia falha junto."""
    async with ctx["sessoes"]() as sessao:
        falhou = await sessao.scalar(
            update(Etapa)
            .where(Etapa.id == etapa_id, Etapa.status == StatusEtapa.EXECUTANDO)
            .values(
                status=StatusEtapa.FALHOU,
                erro="O worker parou duas vezes durante esta etapa.",
                concluida_em=datetime.now(UTC),
            )
            .returning(Etapa.id)
        )
        if falhou is None:
            await sessao.rollback()
            return False
        etapa = await sessao.get(Etapa, etapa_id)
        cadeia = await sessao.get(Cadeia, etapa.cadeia_id, with_for_update=True)
        if cadeia.status not in {StatusCadeia.CANCELADA, StatusCadeia.CONCLUIDA}:
            cadeia.status = StatusCadeia.FALHOU
        await sessao.commit()
        await _publicar(ctx, cadeia, _evento_etapa(etapa))
        await _publicar(ctx, cadeia, _evento_cadeia(cadeia))
    return True
