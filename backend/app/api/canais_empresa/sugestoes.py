"""Sugestões de melhoria dos bots, aprovadas pelo usuário."""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.canais_empresa.comum import (
    RedisDep,
    Sessao,
    Usuario,
    roteador,
)
from app.api.canais_empresa.esquemas import (
    SugestaoEntrada,
    SugestaoSaida,
)
from app.canais_empresa import sugestoes
from app.canais_empresa.eventos import ConhecimentoAtualizado, publicar
from app.canais_empresa.tabelas import (
    SugestaoMelhoria,
)


def _saida_sugestao(s: SugestaoMelhoria) -> SugestaoSaida:
    return SugestaoSaida(
        id=s.id,
        agente_id=s.agente_id,
        tipo=s.tipo,
        titulo=s.titulo,
        motivo=s.motivo,
        texto=s.texto,
        habilidade_nome=s.habilidade_nome,
        conhecimento_ids=s.conhecimento_ids,
        status=s.status,
        aprovacao_id=s.aprovacao_id,
        criada_em=s.criada_em,
        decidida_em=s.decidida_em,
        desfeita_em=s.desfeita_em,
    )


@roteador.get("/sugestoes")
async def listar_sugestoes(
    usuario_id: Usuario,
    sessao: Sessao,
    situacao: Annotated[
        Literal["pendente", "aplicada", "descartada", "desfeita"] | None, Query(alias="status")
    ] = None,
    agente_id: Annotated[UUID | None, Query()] = None,
) -> list[SugestaoSaida]:
    consulta = select(SugestaoMelhoria).where(SugestaoMelhoria.usuario_id == usuario_id)
    if situacao:
        consulta = consulta.where(SugestaoMelhoria.status == situacao)
    if agente_id:
        consulta = consulta.where(SugestaoMelhoria.agente_id == agente_id)
    linhas = await sessao.scalars(
        consulta.order_by(SugestaoMelhoria.criada_em.desc(), SugestaoMelhoria.id).limit(200)
    )
    return [_saida_sugestao(s) for s in linhas.all()]


async def _publicar_sugestao(
    redis: Redis, sessao: AsyncSession, usuario_id: UUID, s: SugestaoMelhoria, motivo: str
) -> None:
    from app.atencao import publicar_estado_atencao

    pendentes = (
        await sessao.scalar(
            select(func.count())
            .select_from(SugestaoMelhoria)
            .where(SugestaoMelhoria.usuario_id == usuario_id, SugestaoMelhoria.status == "pendente")
        )
        or 0
    )
    await publicar_estado_atencao(redis, sessao, usuario_id, agente_id=s.agente_id, grupo_id=None)
    await publicar(
        redis,
        ConhecimentoAtualizado(
            motivo=motivo,  # type: ignore[arg-type]
            sugestao_id=s.id,
            agente_id=s.agente_id,
            sugestoes_pendentes=pendentes,
        ),
        usuario_id,
    )


async def _executar(chamada: Any) -> SugestaoMelhoria:
    try:
        return await chamada
    except sugestoes.ErroSugestao as erro:
        raise HTTPException(erro.status, erro.mensagem) from erro


@roteador.patch("/sugestoes/{sugestao_id}")
async def editar_sugestao(
    sugestao_id: UUID, dados: SugestaoEntrada, usuario_id: Usuario, sessao: Sessao
) -> SugestaoSaida:
    """Editar o texto antes de aplicar (o botão Editar do cartão)."""
    return _saida_sugestao(
        await _executar(sugestoes.editar_texto(sessao, usuario_id, sugestao_id, dados.texto))
    )


@roteador.post("/sugestoes/{sugestao_id}/aplicar")
async def aplicar_sugestao(
    sugestao_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> SugestaoSaida:
    s = await _executar(sugestoes.decidir(sessao, usuario_id, sugestao_id, aplicar=True))
    await sessao.commit()
    await _publicar_sugestao(redis, sessao, usuario_id, s, "aplicacao")
    return _saida_sugestao(s)


@roteador.post("/sugestoes/{sugestao_id}/descartar")
async def descartar_sugestao(
    sugestao_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> SugestaoSaida:
    s = await _executar(sugestoes.decidir(sessao, usuario_id, sugestao_id, aplicar=False))
    await sessao.commit()
    await _publicar_sugestao(redis, sessao, usuario_id, s, "sugestoes")
    return _saida_sugestao(s)


@roteador.post("/sugestoes/{sugestao_id}/desfazer")
async def desfazer_sugestao(
    sugestao_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> SugestaoSaida:
    """Volta o bot (ou a habilidade) à versão de antes do Aplicar."""
    s = await _executar(sugestoes.desfazer(sessao, usuario_id, sugestao_id))
    await sessao.commit()
    await _publicar_sugestao(redis, sessao, usuario_id, s, "desfeita")
    return _saida_sugestao(s)


@roteador.post("/sugestoes/analisar", status_code=status.HTTP_202_ACCEPTED)
async def analisar_agora(usuario_id: Usuario) -> dict[str, bool]:
    """Pede uma rodada de análise já (a rotina semanal continua valendo)."""
    from workers.fila import enfileirar

    await enfileirar(
        "analisar_aprendizado_empresa",
        id_job=f"ce-analise:{usuario_id}:{int(time.time() // 60)}",
        usuario_id=str(usuario_id),
    )
    return {"enfileirada": True}
