"""Rotas de resposta aos cartões de pergunta; especificação §2."""

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
from app.modelos.enumeracoes import StatusEtapa
from app.modelos.esquemas import RespostaPerguntaEntrada
from app.modelos.tabelas import Cadeia, Conversa, Etapa, Pergunta

roteador = APIRouter(prefix="/perguntas", tags=["perguntas"], dependencies=[Depends(usuario_atual)])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]
Usuario = Annotated[UUID, Depends(usuario_atual)]


def obter_fila(redis: RedisDep) -> ArqRedis:
    """Mesmo adaptador de ``api/conversas``: reaproveita o pool Redis da API."""
    return ArqRedis(redis.connection_pool)


Fila = Annotated[ArqRedis, Depends(obter_fila)]


@roteador.post("/{pergunta_id}/responder", status_code=status.HTTP_204_NO_CONTENT)
async def responder_pergunta(
    pergunta_id: UUID,
    dados: RespostaPerguntaEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    fila: Fila,
) -> None:
    """Registra a resposta e retoma a etapa que esperava (a mais antiga da cadeia)."""
    pergunta = await sessao.scalar(
        select(Pergunta)
        .join(Conversa, Conversa.id == Pergunta.conversa_id)
        .where(Pergunta.id == pergunta_id, Conversa.usuario_id == usuario_id)
        .with_for_update(of=Pergunta)
    )
    if pergunta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pergunta não encontrada.")
    if pergunta.respondida_em is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta pergunta já foi respondida.")
    valor = dados.valor.strip()
    if not valor:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Responda a pergunta.")
    valores = {str(o.get("valor")) for o in pergunta.opcoes if isinstance(o, dict)}
    if not pergunta.resposta_livre and valores and valor not in valores:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escolha uma das opções.")

    etapa_id: UUID | None = None
    if pergunta.cadeia_id is not None:
        base_da_cadeia = (
            select(Etapa.id)
            .join(Cadeia, Cadeia.id == Etapa.cadeia_id)
            .where(
                Etapa.cadeia_id == pergunta.cadeia_id,
                Cadeia.usuario_id == usuario_id,
            )
            .order_by(Etapa.ordem, Etapa.id)
            .limit(1)
        )
        # A etapa guarda o id da pergunta que a pausou: com várias etapas esperando, acorda a certa.
        etapa_id = await sessao.scalar(
            base_da_cadeia.where(Etapa.saida["pergunta_id"].astext == str(pergunta_id))
        )
        if etapa_id is None:
            etapa_id = await sessao.scalar(
                base_da_cadeia.where(Etapa.status == StatusEtapa.AGUARDANDO_USUARIO)
            )
    pergunta.resposta = valor
    pergunta.respondida_em = datetime.now(UTC)
    await sessao.commit()
    if etapa_id is not None:
        # Só depois do commit: o worker relê a resposta no banco.
        await fila.enqueue_job(
            "executar_etapa",
            str(etapa_id),
            {"pergunta_id": str(pergunta_id), "valor": valor},
            _job_id=f"pergunta:{pergunta_id}",
        )
    elif pergunta.cadeia_id is None:
        # Pergunta da Sora ou de um agente individual, fora de cadeia: retoma a conversa.
        await fila.enqueue_job(
            "retomar_conversa",
            str(pergunta.conversa_id),
            {"pergunta_id": str(pergunta_id), "valor": valor},
            _job_id=f"pergunta:{pergunta_id}",
        )
