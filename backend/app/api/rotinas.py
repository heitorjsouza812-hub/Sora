"""Rotas das rotinas (Relógio, etapa 4): listar, criar, editar/pausar, apagar, executar agora e
ver as últimas execuções. O contrato está em ``.maestri/contrato-etapa4.md``."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.ferramentas.base import ErroFerramenta
from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import Agente, Rotina, RotinaExecucao
from app.rotinas import servico
from app.rotinas.agenda import MAX_PEDIDO, Agendar

roteador = APIRouter(prefix="/rotinas", tags=["rotinas"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]
RedisDep = Annotated[Redis, Depends(obter_redis)]


class RotinaCriacao(Agendar):
    """Mesmos campos de ``agendar`` + o agente dono (padrão: a Sora) e o fuso."""

    agente_id: UUID | None = None
    fuso: str | None = None


class RotinaAtualizacao(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=120)
    pedido: str | None = Field(default=None, min_length=1, max_length=MAX_PEDIDO)
    silencioso: bool | None = None
    ativa: bool | None = None


class RotinaSaida(BaseModel):
    id: UUID
    agente_id: UUID
    conversa_id: UUID | None
    titulo: str
    pedido: str
    tipo: Literal["unico", "cron", "intervalo"]
    expressao: str | None
    fuso: str
    proxima_execucao: datetime | None
    ultima_execucao: datetime | None
    silencioso: bool
    ativa: bool
    ultimo_status: str | None
    criada_em: datetime


class ExecucaoSaida(BaseModel):
    id: UUID
    rotina_id: UUID
    iniciada_em: datetime
    concluida_em: datetime | None
    status: Literal["executando", "enviada", "silenciosa", "falhou"]
    resumo: str | None
    erro: str | None
    mensagem_id: UUID | None


class ExecucaoAceita(BaseModel):
    execucao_id: UUID


def _saida(rotina: Rotina, ultimo_status: str | None) -> RotinaSaida:
    return RotinaSaida(
        id=rotina.id,
        agente_id=rotina.agente_id,
        conversa_id=rotina.conversa_id,
        titulo=rotina.titulo,
        pedido=rotina.pedido,
        tipo=rotina.tipo,  # type: ignore[arg-type]
        expressao=rotina.expressao,
        fuso=rotina.fuso,
        proxima_execucao=rotina.proxima_execucao,
        ultima_execucao=rotina.ultima_execucao,
        silencioso=rotina.silencioso,
        ativa=rotina.ativa,
        ultimo_status=ultimo_status,
        criada_em=rotina.criada_em,
    )


async def _ultimos_status(sessao: AsyncSession, ids: list[UUID]) -> dict[UUID, str]:
    if not ids:
        return {}
    linhas = (
        await sessao.execute(
            select(RotinaExecucao.rotina_id, RotinaExecucao.status)
            .where(RotinaExecucao.rotina_id.in_(ids))
            .order_by(RotinaExecucao.rotina_id, RotinaExecucao.iniciada_em.desc())
            .distinct(RotinaExecucao.rotina_id)
        )
    ).all()
    return {rotina_id: estado for rotina_id, estado in linhas}


async def _obter(sessao: AsyncSession, usuario_id: UUID, rotina_id: UUID) -> Rotina:
    rotina = await servico.obter(sessao, usuario_id, rotina_id)
    if rotina is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rotina não encontrada.")
    return rotina


async def _um_status(sessao: AsyncSession, rotina: Rotina) -> str | None:
    return (await _ultimos_status(sessao, [rotina.id])).get(rotina.id)


@roteador.get("")
async def listar_rotinas(usuario_id: UsuarioId, sessao: Sessao) -> list[RotinaSaida]:
    rotinas = await servico.listar(sessao, usuario_id)
    estados = await _ultimos_status(sessao, [r.id for r in rotinas])
    return [_saida(r, estados.get(r.id)) for r in rotinas]


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def criar_rotina(dados: RotinaCriacao, usuario_id: UsuarioId, sessao: Sessao) -> RotinaSaida:
    agente_id = dados.agente_id
    if agente_id is None:
        agente_id = await sessao.scalar(
            select(Agente.id).where(
                Agente.usuario_id == usuario_id,
                Agente.tipo == TipoAgente.SORA,
                Agente.apagado_em.is_(None),
            )
        )
        if agente_id is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "A Sora desta conta ainda não existe.")
    try:
        rotina = await servico.criar(
            sessao,
            usuario_id=usuario_id,
            agente_id=agente_id,
            conversa_id=None,
            args=Agendar.model_validate(dados.model_dump(exclude={"agente_id", "fuso"})),
            fuso=dados.fuso,
        )
    except ErroFerramenta as erro:
        codigo = 404 if "não encontrado" in str(erro) else 422
        raise HTTPException(codigo, str(erro)) from erro
    return _saida(rotina, None)


@roteador.patch("/{rotina_id}")
async def atualizar_rotina(
    rotina_id: UUID, dados: RotinaAtualizacao, usuario_id: UsuarioId, sessao: Sessao
) -> RotinaSaida:
    rotina = await _obter(sessao, usuario_id, rotina_id)
    if dados.titulo is not None:
        rotina.titulo = dados.titulo.strip()
    if dados.pedido is not None:
        rotina.pedido = dados.pedido.strip()
    if dados.silencioso is not None:
        rotina.silencioso = dados.silencioso
    if dados.ativa is True and not rotina.ativa:
        await servico.retomar(rotina)
        if not rotina.ativa:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Essa rotina de uma execução só já passou do horário."
            )
    elif dados.ativa is False:
        rotina.ativa = False
    await sessao.flush()
    return _saida(rotina, await _um_status(sessao, rotina))


@roteador.delete("/{rotina_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_rotina(rotina_id: UUID, usuario_id: UsuarioId, sessao: Sessao) -> None:
    rotina = await _obter(sessao, usuario_id, rotina_id)
    await sessao.delete(rotina)


@roteador.post("/{rotina_id}/executar", status_code=status.HTTP_202_ACCEPTED)
async def executar_agora(
    rotina_id: UUID, usuario_id: UsuarioId, sessao: Sessao, redis: RedisDep
) -> ExecucaoAceita:
    rotina = await _obter(sessao, usuario_id, rotina_id)
    execucao = RotinaExecucao(id=uuid4(), rotina_id=rotina.id, usuario_id=usuario_id)
    sessao.add(execucao)
    await sessao.commit()
    fila = ArqRedis(redis.connection_pool)
    await fila.enqueue_job(
        "executar_rotina",
        rotina_id=str(rotina.id),
        execucao_id=str(execucao.id),
        manual=True,
        _job_id=f"rotina-manual:{execucao.id}",
    )
    return ExecucaoAceita(execucao_id=execucao.id)


@roteador.get("/{rotina_id}/execucoes")
async def listar_execucoes(
    rotina_id: UUID,
    usuario_id: UsuarioId,
    sessao: Sessao,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ExecucaoSaida]:
    await _obter(sessao, usuario_id, rotina_id)
    return [
        ExecucaoSaida.model_validate(e, from_attributes=True)
        for e in await servico.ultimas_execucoes(sessao, rotina_id, limite)
    ]
