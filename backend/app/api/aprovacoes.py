"""Rotas dos cartões de aprovação; especificação §§2 e 6.1."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.eventos.streams import publicar_evento
from app.eventos.tipos import AprovacaoResolvida
from app.modelos.enumeracoes import DecisaoAprovacao, StatusAprovacao
from app.modelos.esquemas import DecisaoAprovacaoEntrada
from app.modelos.tabelas import Aprovacao, Cadeia, Conversa, Etapa, RegraPermissao

roteador = APIRouter(
    prefix="/aprovacoes", tags=["aprovacoes"], dependencies=[Depends(usuario_atual)]
)

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]
Usuario = Annotated[UUID, Depends(usuario_atual)]


def obter_fila(redis: RedisDep) -> ArqRedis:
    """Mesmo adaptador de ``api/conversas``: reaproveita o pool Redis da API."""
    return ArqRedis(redis.connection_pool)


Fila = Annotated[ArqRedis, Depends(obter_fila)]


@roteador.post("/{aprovacao_id}/decidir", status_code=status.HTTP_204_NO_CONTENT)
async def decidir_aprovacao(
    aprovacao_id: UUID,
    dados: DecisaoAprovacaoEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
    fila: Fila,
) -> None:
    """Registra a decisão e retoma a etapa interrompida.

    ``sempre_permitir`` também grava uma ``regras_permissao`` para o agente e a ferramenta.
    """
    aprovacao = await sessao.scalar(
        select(Aprovacao)
        .where(Aprovacao.id == aprovacao_id, Aprovacao.usuario_id == usuario_id)
        .with_for_update()
    )
    if aprovacao is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aprovação não encontrada.")
    agora = datetime.now(UTC)
    if aprovacao.status != StatusAprovacao.PENDENTE or aprovacao.expira_em <= agora:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este pedido não está mais pendente.")

    negada = dados.decisao == DecisaoAprovacao.NEGAR
    aprovacao.status = StatusAprovacao.NEGADA if negada else StatusAprovacao.PERMITIDA
    aprovacao.decidida_em = agora
    ferramenta = aprovacao.acao.get("ferramenta") if isinstance(aprovacao.acao, dict) else None
    if dados.decisao == DecisaoAprovacao.SEMPRE_PERMITIR and isinstance(ferramenta, str):
        condicao = aprovacao.acao.get("condicao")
        sessao.add(
            RegraPermissao(
                usuario_id=usuario_id,
                agente_id=aprovacao.agente_id,
                ferramenta=ferramenta,
                condicao=condicao if isinstance(condicao, dict) else {},
            )
        )
    conversa_id = None
    if aprovacao.etapa_id is not None:
        conversa_id = await sessao.scalar(
            select(Cadeia.conversa_id)
            .join(Etapa, Etapa.cadeia_id == Cadeia.id)
            .where(Etapa.id == aprovacao.etapa_id, Cadeia.usuario_id == usuario_id)
        )
    conversa_fora_de_cadeia: UUID | None = None
    if aprovacao.etapa_id is None and isinstance(aprovacao.acao, dict):
        # Aprovação pedida pela Sora ou por um agente individual, fora de cadeia: a conversa
        # vem no próprio cartão (``acao.conversa_id``) e precisa ser do usuário.
        try:
            candidata = UUID(str(aprovacao.acao.get("conversa_id")))
        except ValueError:
            candidata = None
        if candidata is not None:
            conversa_fora_de_cadeia = await sessao.scalar(
                select(Conversa.id).where(
                    Conversa.id == candidata, Conversa.usuario_id == usuario_id
                )
            )
            conversa_id = conversa_fora_de_cadeia
    novo_status = aprovacao.status
    etapa_id = aprovacao.etapa_id
    await sessao.commit()
    # Evento e job só depois do commit; o worker relê a decisão no banco.
    if conversa_id is not None:
        await publicar_evento(
            redis,
            AprovacaoResolvida(aprovacao_id=aprovacao_id, status=novo_status),
            conversa_id,
            usuario_id,
        )
    if etapa_id is not None:
        await fila.enqueue_job(
            "executar_etapa",
            str(etapa_id),
            {"aprovacao_id": str(aprovacao_id), "decisao": dados.decisao.value},
            _job_id=f"aprovacao:{aprovacao_id}",
        )
    elif conversa_fora_de_cadeia is not None:
        await fila.enqueue_job(
            "retomar_conversa",
            str(conversa_fora_de_cadeia),
            {"aprovacao_id": str(aprovacao_id), "decisao": dados.decisao.value},
            _job_id=f"aprovacao:{aprovacao_id}",
        )
