"""Rotas de agentes individuais e especialistas; especificação §2."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentes.aparencia import (
    COR_SORA,
    escolher_cor,
    escolher_nome,
    movimento_do_individual,
)
from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.ferramentas.permissoes import FERRAMENTAS_POR_PAPEL
from app.modelos.enumeracoes import TipoAgente
from app.modelos.esquemas import (
    AgenteAtualizacao,
    AgenteCriacao,
    AgentePorDescricao,
    AgenteSaida,
)
from app.modelos.tabelas import Agente, Etapa, Usuario
from app.orquestrador.estados import status_do_agente

roteador = APIRouter(prefix="/agentes", tags=["agentes"], dependencies=[Depends(usuario_atual)])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]

LIMITE_INDIVIDUAIS = 5
FUNCAO_MAX = 80
FERRAMENTAS_CONHECIDAS = frozenset(n for lista in FERRAMENTAS_POR_PAPEL.values() for n in lista)


def _saida(agente: Agente, status_app: str | None = None) -> AgenteSaida:
    return AgenteSaida(
        id=agente.id,
        tipo=agente.tipo,
        nome=agente.nome,
        funcao=agente.funcao,
        cor=agente.cor,
        movimento=agente.movimento,
        status=status_app,
    )


async def _obter(sessao: AsyncSession, usuario_id: UUID, agente_id: UUID) -> Agente:
    agente = await sessao.scalar(
        select(Agente).where(
            Agente.id == agente_id, Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None)
        )
    )
    if agente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente não encontrado.")
    return agente


async def _garantir_vaga(sessao: AsyncSession, usuario_id: UUID) -> None:
    """Serializa por usuário (trava a linha dele) e confere o teto de 5 individuais."""
    await sessao.scalar(select(Usuario.id).where(Usuario.id == usuario_id).with_for_update())
    total = await sessao.scalar(
        select(func.count())
        .select_from(Agente)
        .where(
            Agente.usuario_id == usuario_id,
            Agente.tipo == TipoAgente.INDIVIDUAL,
            Agente.apagado_em.is_(None),
        )
    )
    if (total or 0) >= LIMITE_INDIVIDUAIS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Você já tem {LIMITE_INDIVIDUAIS} agentes. Apague um para criar outro.",
        )


async def _em_uso(sessao: AsyncSession, usuario_id: UUID) -> tuple[set[str], set[str]]:
    linhas = (
        await sessao.execute(
            select(Agente.nome, Agente.cor).where(
                Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None)
            )
        )
    ).all()
    return {n for n, _ in linhas}, {c for _, c in linhas}


def _validar_ferramentas(ferramentas: list[str]) -> list[str]:
    desconhecidas = sorted(set(ferramentas) - FERRAMENTAS_CONHECIDAS)
    if desconhecidas:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Ferramentas desconhecidas: " + ", ".join(desconhecidas),
        )
    return list(dict.fromkeys(ferramentas))


def _validar_cor(cor: str) -> str:
    cor = cor.strip()
    try:
        valida = len(cor) == 7 and cor.startswith("#") and int(cor[1:], 16) >= 0
    except ValueError:
        valida = False
    if not valida:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use uma cor como #46E8A8.")
    if cor.upper() == COR_SORA:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Essa cor é da Sora.")
    return cor.upper()


def _funcao_da_descricao(descricao: str) -> str:
    primeira = descricao.strip().splitlines()[0].strip()
    primeira = primeira.split(". ")[0].rstrip(".")
    return primeira[:FUNCAO_MAX].rstrip()


@roteador.get("")
async def listar_agentes(
    usuario_id: UsuarioId, sessao: Sessao, tipo: TipoAgente | None = None
) -> list[AgenteSaida]:
    """Lista agentes do usuário, opcionalmente filtrados por tipo."""
    consulta = select(Agente).where(Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None))
    if tipo is not None:
        consulta = consulta.where(Agente.tipo == tipo)
    agentes = list((await sessao.scalars(consulta.order_by(Agente.criado_em, Agente.id))).all())
    ultima: dict[UUID, Etapa] = {}
    if agentes:
        etapas = await sessao.scalars(
            select(Etapa)
            .where(Etapa.agente_id.in_([a.id for a in agentes]))
            .order_by(Etapa.iniciada_em.nullsfirst(), Etapa.ordem)
        )
        for etapa in etapas:
            if etapa.agente_id is not None:
                ultima[etapa.agente_id] = etapa
    return [
        _saida(a, status_do_agente(ultima[a.id].status).value if a.id in ultima else None)
        for a in agentes
    ]


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def criar_agente(dados: AgenteCriacao, usuario_id: UsuarioId, sessao: Sessao) -> AgenteSaida:
    """Cria um agente individual configurado, ou monta o perfil a partir da descrição."""
    await _garantir_vaga(sessao, usuario_id)
    nomes, cores = await _em_uso(sessao, usuario_id)
    if isinstance(dados, AgentePorDescricao):
        descricao = dados.descricao.strip()
        if not descricao:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Descreva o agente.")
        agente = Agente(
            usuario_id=usuario_id,
            tipo=TipoAgente.INDIVIDUAL,
            nome=escolher_nome(nomes),
            funcao=_funcao_da_descricao(descricao),
            papel=descricao,
            cor=escolher_cor(cores),
            movimento=movimento_do_individual(descricao),
            ferramentas=list(FERRAMENTAS_POR_PAPEL["individual"]),
        )
    else:
        nome = dados.nome.strip()
        if not nome or nome.casefold() == "sora":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escolha outro nome.")
        if nome.casefold() in {n.casefold() for n in nomes}:
            raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um agente com esse nome.")
        agente = Agente(
            usuario_id=usuario_id,
            tipo=TipoAgente.INDIVIDUAL,
            nome=nome,
            funcao=dados.funcao.strip(),
            papel=dados.papel.strip(),
            cor=_validar_cor(dados.cor) if dados.cor else escolher_cor(cores),
            movimento=dados.movimento or movimento_do_individual(dados.funcao),
            ferramentas=_validar_ferramentas(dados.ferramentas)
            or list(FERRAMENTAS_POR_PAPEL["individual"]),
        )
    sessao.add(agente)
    await sessao.flush()
    saida = _saida(agente)
    await sessao.commit()
    return saida


@roteador.post("/{agente_id}/promover")
async def promover_agente(agente_id: UUID, usuario_id: UsuarioId, sessao: Sessao) -> AgenteSaida:
    """Salvar como agente: o especialista vira individual (e passa a contar no teto de 5)."""
    agente = await _obter(sessao, usuario_id, agente_id)
    if agente.tipo != TipoAgente.ESPECIALISTA:
        raise HTTPException(status.HTTP_409_CONFLICT, "Só especialistas podem ser promovidos.")
    await _garantir_vaga(sessao, usuario_id)
    agente.tipo = TipoAgente.INDIVIDUAL
    if not agente.ferramentas:
        agente.ferramentas = list(FERRAMENTAS_POR_PAPEL["individual"])
    saida = _saida(agente)
    await sessao.commit()
    return saida


@roteador.patch("/{agente_id}")
async def atualizar_agente(
    agente_id: UUID, dados: AgenteAtualizacao, usuario_id: UsuarioId, sessao: Sessao
) -> AgenteSaida:
    """Atualiza os campos editáveis; a Sora não é editável."""
    agente = await _obter(sessao, usuario_id, agente_id)
    if agente.tipo == TipoAgente.SORA:
        raise HTTPException(status.HTTP_409_CONFLICT, "A Sora não pode ser alterada.")
    campos = dados.model_fields_set
    if "nome" in campos:
        nome = (dados.nome or "").strip()
        if not nome or nome.casefold() == "sora":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escolha outro nome.")
        nomes, _ = await _em_uso(sessao, usuario_id)
        if nome.casefold() in {n.casefold() for n in nomes} - {agente.nome.casefold()}:
            raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um agente com esse nome.")
        agente.nome = nome
    if dados.funcao is not None:
        agente.funcao = dados.funcao.strip()
    if dados.papel is not None:
        agente.papel = dados.papel.strip()
    if dados.cor is not None:
        agente.cor = _validar_cor(dados.cor)
    if dados.movimento is not None:
        agente.movimento = dados.movimento
    if "modelo_padrao" in campos:
        agente.modelo_padrao = (dados.modelo_padrao or "").strip() or None
    saida = _saida(agente)
    await sessao.commit()
    return saida


@roteador.delete("/{agente_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_agente(agente_id: UUID, usuario_id: UsuarioId, sessao: Sessao) -> None:
    """Marca um agente individual como apagado (exclusão lógica)."""
    agente = await _obter(sessao, usuario_id, agente_id)
    if agente.tipo != TipoAgente.INDIVIDUAL:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Só agentes individuais podem ser apagados aqui."
        )
    agente.apagado_em = func.now()
    await sessao.commit()
