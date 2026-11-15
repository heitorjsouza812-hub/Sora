"""Rascunhos de bot: sugerir, confirmar atomicamente ou descartar."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentes.aparencia import movimento_do_individual
from app.api.agentes import (
    _em_uso,
    _garantir_vaga,
    _saida,
    _validar_cor,
    _validar_ferramentas,
)
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.eventos.equipe import (
    BotRascunhoEvento,
    BotRascunhoResolvido,
    publicar_evento_equipe,
)
from app.ferramentas.base import ErroFerramenta
from app.modelos.enumeracoes import TipoAgente
from app.modelos.esquemas import AgenteSaida
from app.modelos.tabelas import Agente, PropostaGrupo, RascunhoBot
from app.rascunhos_bot import (
    RascunhoBotAjuste,
    RascunhoBotSaida,
    criar_rascunho,
    obter_rascunho_para_atualizar,
    resolver,
    saida_do_rascunho,
)
from app.rotinas import servico as servico_rotinas
from app.rotinas.agenda import Agendar

roteador = APIRouter(prefix="/bots/rascunhos", tags=["bots"], dependencies=[Depends(usuario_atual)])
Usuario = Annotated[UUID, Depends(usuario_atual)]
Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]


class RascunhoBotCriacao(BaseModel):
    descricao: str = Field(min_length=1, max_length=2_000)


def _aplicar_ajustes(rascunho, ajustes: RascunhoBotAjuste) -> None:
    dados = dict(rascunho.dados)
    serializados = ajustes.model_dump(mode="json", exclude_unset=True)
    for campo in ("nome", "funcao", "cor", "instrucoes", "ferramentas", "rotina"):
        if campo in ajustes.model_fields_set:
            dados[campo] = serializados[campo]
    rascunho.dados = dados


async def _materializar_rascunho(sessao: AsyncSession, usuario_id: UUID, rascunho) -> Agente:
    dados = dict(rascunho.dados)
    nome = str(dados.get("nome") or "").strip()
    funcao = str(dados.get("funcao") or "").strip()
    instrucoes = str(dados.get("instrucoes") or "").strip()
    if not nome or nome.casefold() == "sora" or not funcao:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Informe nome e função do bot.")
    nomes, _ = await _em_uso(sessao, usuario_id)
    if nome.casefold() in {existente.casefold() for existente in nomes}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um bot com esse nome.")
    cor = _validar_cor(str(dados.get("cor") or ""))
    ferramentas = _validar_ferramentas(list(dados.get("ferramentas") or []))
    agente = Agente(
        usuario_id=usuario_id,
        tipo=TipoAgente.INDIVIDUAL,
        nome=nome,
        funcao=funcao,
        papel=instrucoes or funcao,
        instrucoes=instrucoes,
        cor=cor,
        movimento=movimento_do_individual(funcao),
        ferramentas=ferramentas,
    )
    sessao.add(agente)
    await sessao.flush()

    rotina = dados.get("rotina")
    if rotina is not None:
        rotina = dict(rotina)
        try:
            await servico_rotinas.criar(
                sessao,
                usuario_id=usuario_id,
                agente_id=agente.id,
                conversa_id=rascunho.conversa_id,
                args=Agendar(
                    titulo=f"Rotina de {nome}",
                    pedido=rotina["descricao"],
                    cron=rotina["agendamento"],
                ),
                fuso=rotina["fuso"],
            )
        except (ErroFerramenta, KeyError, ValueError) as erro:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro
    resolver(rascunho, "confirmado")
    rascunho.agente_id = agente.id
    return agente


async def _ids_em_propostas(sessao: AsyncSession, usuario_id: UUID) -> set[str]:
    return {
        str(item.get("id"))
        for bots_novos in await sessao.scalars(
            select(PropostaGrupo.bots_novos).where(
                PropostaGrupo.usuario_id == usuario_id, PropostaGrupo.status == "proposta"
            )
        )
        for item in bots_novos or []
    }


async def _recusar_se_de_proposta(sessao: AsyncSession, usuario_id: UUID, rascunho_id) -> None:
    if str(rascunho_id) in await _ids_em_propostas(sessao, usuario_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Esse bot faz parte de uma proposta de grupo; decida pelo cartão da proposta.",
        )


@roteador.get("")
async def listar(usuario_id: Usuario, sessao: Sessao) -> list[RascunhoBotSaida]:
    """Rascunhos ainda pendentes do usuário, na ordem de criação (recarga do cartão)."""
    rascunhos = await sessao.scalars(
        select(RascunhoBot)
        .where(RascunhoBot.usuario_id == usuario_id, RascunhoBot.status == "rascunho")
        .order_by(RascunhoBot.criado_em, RascunhoBot.id)
    )
    # Bot novo de proposta de grupo pendente aparece no cartão da proposta, não sozinho.
    da_proposta = await _ids_em_propostas(sessao, usuario_id)
    return [
        saida_do_rascunho(rascunho) for rascunho in rascunhos if str(rascunho.id) not in da_proposta
    ]


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def criar(
    dados: RascunhoBotCriacao, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> RascunhoBotSaida:
    rascunho = await criar_rascunho(sessao, usuario_id, descricao=dados.descricao)
    saida = saida_do_rascunho(rascunho)
    await sessao.commit()
    await publicar_evento_equipe(redis, BotRascunhoEvento.de(saida), usuario_id)
    return saida


@roteador.post("/{rascunho_id}/confirmar", status_code=status.HTTP_201_CREATED)
async def confirmar(
    rascunho_id: UUID,
    ajustes: RascunhoBotAjuste,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
) -> AgenteSaida:
    rascunho = await obter_rascunho_para_atualizar(sessao, usuario_id, rascunho_id)
    if rascunho is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rascunho não encontrado.")
    if rascunho.status != "rascunho":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esse rascunho já foi resolvido.")
    await _recusar_se_de_proposta(sessao, usuario_id, rascunho.id)
    await _garantir_vaga(sessao, usuario_id)
    _aplicar_ajustes(rascunho, ajustes)
    agente = await _materializar_rascunho(sessao, usuario_id, rascunho)
    saida = _saida(agente)
    await sessao.commit()
    await publicar_evento_equipe(
        redis,
        BotRascunhoResolvido(rascunho_id=rascunho.id, status="confirmado", agente_id=agente.id),
        usuario_id,
    )
    return saida


@roteador.delete("/{rascunho_id}", status_code=status.HTTP_204_NO_CONTENT)
async def descartar(
    rascunho_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> None:
    rascunho = await obter_rascunho_para_atualizar(sessao, usuario_id, rascunho_id)
    if rascunho is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rascunho não encontrado.")
    if rascunho.status != "rascunho":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esse rascunho já foi resolvido.")
    await _recusar_se_de_proposta(sessao, usuario_id, rascunho.id)
    resolver(rascunho, "descartado")
    await sessao.commit()
    await publicar_evento_equipe(
        redis,
        BotRascunhoResolvido(rascunho_id=rascunho.id, status="descartado"),
        usuario_id,
    )
