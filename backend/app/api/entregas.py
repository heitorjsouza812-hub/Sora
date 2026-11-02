"""Rotas de entregas e versões da revisão; especificação §2."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.modelos.esquemas import EntregaSaida, EntregasListaSaida
from app.modelos.tabelas import Conversa, Entrega

roteador = APIRouter(tags=["entregas"], dependencies=[Depends(usuario_atual)])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
Usuario = Annotated[UUID, Depends(usuario_atual)]


@roteador.get("/conversas/{conversa_id}/entregas")
async def listar_entregas(
    conversa_id: UUID, usuario_id: Usuario, sessao: Sessao, versao: int | None = None
) -> EntregasListaSaida:
    """Lista entregas de uma versão (padrão: a mais nova) e todas as versões disponíveis."""
    dona = await sessao.scalar(
        select(Conversa.id).where(Conversa.id == conversa_id, Conversa.usuario_id == usuario_id)
    )
    if dona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada.")
    versoes = sorted(
        set(
            (
                await sessao.scalars(
                    select(Entrega.versao).where(
                        Entrega.conversa_id == conversa_id, Entrega.usuario_id == usuario_id
                    )
                )
            ).all()
        )
    )
    if versao is None:
        escolhida = versoes[-1] if versoes else None
    elif versao in versoes:
        escolhida = versao
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Versão não encontrada.")
    if escolhida is None:
        return EntregasListaSaida(entregas=[], versoes=[])
    linhas = (
        await sessao.scalars(
            select(Entrega)
            .where(
                Entrega.conversa_id == conversa_id,
                Entrega.usuario_id == usuario_id,
                Entrega.versao == escolhida,
            )
            .order_by(Entrega.criada_em, Entrega.id)
        )
    ).all()
    return EntregasListaSaida(
        entregas=[
            EntregaSaida(
                id=e.id,
                agente_id=e.agente_id,
                versao=e.versao,
                tipo=e.tipo,
                titulo=e.titulo,
                resumo=e.resumo,
                conteudo=e.conteudo,
            )
            for e in linhas
        ],
        versoes=versoes,
    )
