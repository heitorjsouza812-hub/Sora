"""Rotas de agentes individuais e especialistas; especificação §2."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentes.aparencia import (
    COR_SORA,
    escolher_cor,
    escolher_nome,
    movimento_do_individual,
)
from app.computador.ferramentas import NOMES as FERRAMENTAS_DO_COMPUTADOR
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.estado_interface import EstadoInterface, estados_dos_agentes, estados_dos_grupos
from app.ferramentas.permissoes import FERRAMENTAS_POR_PAPEL, ferramentas_do_agente
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
RedisDep = Annotated[Redis, Depends(obter_redis)]

FUNCAO_MAX = 80
FERRAMENTAS_CONHECIDAS = frozenset(n for lista in FERRAMENTAS_POR_PAPEL.values() for n in lista) | {
    *FERRAMENTAS_DO_COMPUTADOR  # Farol (C2): o bot liga o computador virtual por ferramenta extra
}


def _saida(
    agente: Agente,
    status_app: str | None = None,
    estado: EstadoInterface = "livre",
) -> AgenteSaida:
    return AgenteSaida(
        id=agente.id,
        tipo=agente.tipo,
        nome=agente.nome,
        funcao=agente.funcao,
        cor=agente.cor,
        movimento=agente.movimento,
        status=status_app,
        ferramentas=ferramentas_do_agente(
            "sora" if agente.tipo == TipoAgente.SORA else agente.papel, agente.ferramentas
        ),
        estado=estado,
        perfil_navegador=(
            "perfil" if agente.perfil_navegador == "nomeado" else agente.perfil_navegador
        ),
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


async def _sora_persistente(sessao: AsyncSession, usuario_id: UUID) -> Agente:
    """Obtém a Sora da conta e repara contas antigas sob trava da linha do usuário."""
    await sessao.scalar(select(Usuario.id).where(Usuario.id == usuario_id).with_for_update())
    sora = await sessao.scalar(
        select(Agente).where(
            Agente.usuario_id == usuario_id,
            Agente.tipo == TipoAgente.SORA,
            Agente.apagado_em.is_(None),
        )
    )
    if sora is None:
        sora = Agente(
            usuario_id=usuario_id,
            tipo=TipoAgente.SORA,
            nome="Sora",
            funcao="Coordena seus bots e grupos",
            papel="sora",
            perfil_navegador="compartilhado",  # a Sora usa o login da conta; bots, o próprio
            cor=COR_SORA,
            ferramentas=list(FERRAMENTAS_POR_PAPEL["sora"]),
        )
        sessao.add(sora)
        await sessao.flush()
    return sora


async def _garantir_vaga(sessao: AsyncSession, usuario_id: UUID) -> None:
    """Serializa a criação de bots do usuário (trava a linha dele). Não há teto de bots."""
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
    del total  # sem teto de bots (decisão do Heitor, 2026-11-08); a trava serializa a criação


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
    estados = await estados_dos_agentes(sessao, usuario_id, [agente.id for agente in agentes])
    return [
        _saida(
            a,
            status_do_agente(ultima[a.id].status).value if a.id in ultima else None,
            estados[a.id],
        )
        for a in agentes
    ]


@roteador.get("/sora")
async def obter_sora(usuario_id: UsuarioId, sessao: Sessao) -> AgenteSaida:
    sora = await _sora_persistente(sessao, usuario_id)
    estado = (await estados_dos_agentes(sessao, usuario_id, [sora.id]))[sora.id]
    await sessao.commit()
    return _saida(sora, estado=estado)


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
    """Salvar como agente: o especialista vira individual (passa a ser um bot do usuário)."""
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


async def _tirar_dos_grupos(sessao: AsyncSession, usuario_id: UUID, agente: Agente):
    """Bot apagado sai de todos os grupos e o trabalho dele é cancelado."""
    from app.canais_equipe.servico import Mudancas, ServicoCanais
    from app.canais_equipe.sql import ArmazemCanaisSQL

    armazem = ArmazemCanaisSQL(sessao)
    servico = ServicoCanais(armazem)
    total = Mudancas()
    for canal in await armazem.canais_do_usuario(usuario_id):
        if agente.id not in canal.membros:
            continue
        mudancas = await servico.remover_agente_apagado(
            canal.id, usuario_id, agente.id, agente.nome
        )
        total.mensagens.extend(mudancas.mensagens)
        total.tarefas.extend(mudancas.tarefas)
        total.interromper.extend(mudancas.interromper)
    return total if total.mensagens or total.tarefas else None


@roteador.delete("/{agente_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_agente(
    agente_id: UUID, usuario_id: UsuarioId, sessao: Sessao, redis: RedisDep
) -> None:
    """Marca um agente individual como apagado (exclusão lógica)."""
    agente = await _obter(sessao, usuario_id, agente_id)
    if agente.tipo != TipoAgente.INDIVIDUAL:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Só agentes individuais podem ser apagados aqui."
        )
    agente.apagado_em = func.now()
    mudancas = await _tirar_dos_grupos(sessao, usuario_id, agente)
    from app.atencao import encerrar_pendentes, publicar_encerrados

    afetados = await encerrar_pendentes(sessao, usuario_id, agente_id=agente.id)
    await sessao.commit()
    await publicar_encerrados(redis, sessao, usuario_id, afetados)
    if mudancas is not None:
        from app.api.equipe import _publicar_mudancas
        from app.api.grupos import _evento
        from app.canais_equipe.sql import ArmazemCanaisSQL
        from app.eventos.equipe import publicar_evento_equipe

        await _publicar_mudancas(redis, usuario_id, mudancas)
        armazem = ArmazemCanaisSQL(sessao)
        canais = {mensagem.canal_id for mensagem in mudancas.mensagens}
        estados = await estados_dos_grupos(sessao, usuario_id, list(canais))
        for canal_id in canais:
            canal = await armazem.canal(canal_id)
            if canal is not None and canal.lider_id is not None:
                await publicar_evento_equipe(redis, _evento(canal, estados[canal_id]), usuario_id)
