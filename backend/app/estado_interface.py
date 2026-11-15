"""Estado resumido de bots e grupos para a interface da etapa 5.

O estado é derivado do trabalho persistido. Não existe relógio nem simulação: uma atenção
pendente prevalece sobre trabalho ativo, e trabalho ativo prevalece sobre ``livre``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.enumeracoes import StatusAprovacao, StatusEtapa
from app.modelos.tabelas import (
    Agente,
    Aprovacao,
    CanalEquipe,
    Conversa,
    Etapa,
    MembroCanal,
    Pergunta,
    TarefaCanalTabela,
)

EstadoInterface = Literal["livre", "trabalhando", "precisa_de_voce"]

_TAREFAS_ATIVAS = ("na_fila", "rodando", "aguardando_filhas")
_TAREFAS_ATENCAO = ("parada", "falhou")


async def estados_dos_agentes(
    sessao: AsyncSession, usuario_id: UUID, agente_ids: list[UUID]
) -> dict[UUID, EstadoInterface]:
    estados: dict[UUID, EstadoInterface] = {agente_id: "livre" for agente_id in agente_ids}
    if not agente_ids:
        return estados

    ativos = await sessao.scalars(
        select(Etapa.agente_id).where(
            Etapa.agente_id.in_(agente_ids),
            Etapa.status.in_([StatusEtapa.PENDENTE, StatusEtapa.EXECUTANDO]),
        )
    )
    for agente_id in ativos:
        if agente_id is not None:
            estados[agente_id] = "trabalhando"

    tarefas = await sessao.execute(
        select(TarefaCanalTabela.dono_id, TarefaCanalTabela.status)
        .join(CanalEquipe, CanalEquipe.id == TarefaCanalTabela.canal_id)
        .where(
            CanalEquipe.usuario_id == usuario_id,
            TarefaCanalTabela.dono_id.in_(agente_ids),
            TarefaCanalTabela.status.in_([*_TAREFAS_ATIVAS, *_TAREFAS_ATENCAO]),
        )
    )
    for agente_id, status in tarefas:
        estados[agente_id] = "precisa_de_voce" if status in _TAREFAS_ATENCAO else estados[agente_id]
        if estados[agente_id] == "livre":
            estados[agente_id] = "trabalhando"

    aprovacoes = await sessao.scalars(
        select(Aprovacao.agente_id).where(
            Aprovacao.usuario_id == usuario_id,
            Aprovacao.agente_id.in_(agente_ids),
            Aprovacao.status == StatusAprovacao.PENDENTE,
            Aprovacao.expira_em > datetime.now(UTC),
        )
    )
    for agente_id in aprovacoes:
        estados[agente_id] = "precisa_de_voce"

    perguntas = await sessao.scalars(
        select(Conversa.agente_id)
        .join(Pergunta, Pergunta.conversa_id == Conversa.id)
        .where(
            Conversa.usuario_id == usuario_id,
            Conversa.agente_id.in_(agente_ids),
            Pergunta.respondida_em.is_(None),
        )
    )
    for agente_id in perguntas:
        estados[agente_id] = "precisa_de_voce"
    return estados


async def estados_dos_grupos(
    sessao: AsyncSession, usuario_id: UUID, grupo_ids: list[UUID]
) -> dict[UUID, EstadoInterface]:
    estados: dict[UUID, EstadoInterface] = {grupo_id: "livre" for grupo_id in grupo_ids}
    if not grupo_ids:
        return estados
    # Só conta trabalho de quem ainda é membro e existe: bot apagado não prende o grupo.
    tarefas = await sessao.execute(
        select(TarefaCanalTabela.canal_id, TarefaCanalTabela.status)
        .join(
            MembroCanal,
            (MembroCanal.canal_id == TarefaCanalTabela.canal_id)
            & (MembroCanal.agente_id == TarefaCanalTabela.dono_id),
        )
        .join(Agente, Agente.id == TarefaCanalTabela.dono_id)
        .where(
            TarefaCanalTabela.canal_id.in_(grupo_ids),
            TarefaCanalTabela.status.in_([*_TAREFAS_ATIVAS, *_TAREFAS_ATENCAO]),
            Agente.apagado_em.is_(None),
        )
    )
    for grupo_id, status in tarefas:
        if status in _TAREFAS_ATENCAO:
            estados[grupo_id] = "precisa_de_voce"
        elif estados[grupo_id] == "livre":
            estados[grupo_id] = "trabalhando"

    # Aprovação de um membro também destaca o grupo. A consulta fica restrita à conta dona.
    aprovacoes = await sessao.scalars(
        select(MembroCanal.canal_id)
        .join(CanalEquipe, CanalEquipe.id == MembroCanal.canal_id)
        .join(Aprovacao, Aprovacao.agente_id == MembroCanal.agente_id)
        .where(
            CanalEquipe.usuario_id == usuario_id,
            MembroCanal.canal_id.in_(grupo_ids),
            Aprovacao.status == StatusAprovacao.PENDENTE,
            Aprovacao.expira_em > datetime.now(UTC),
        )
    )
    for grupo_id in aprovacoes:
        estados[grupo_id] = "precisa_de_voce"
    perguntas = await sessao.scalars(
        select(Pergunta.grupo_id)
        .join(Conversa, Conversa.id == Pergunta.conversa_id)
        .where(
            Conversa.usuario_id == usuario_id,
            Pergunta.grupo_id.in_(grupo_ids),
            Pergunta.respondida_em.is_(None),
        )
    )
    for grupo_id in perguntas:
        if grupo_id is not None:
            estados[grupo_id] = "precisa_de_voce"
    return estados
