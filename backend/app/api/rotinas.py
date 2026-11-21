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


MAX_PEDIDO_SEGUINTE = 2000


class RotinaCriacao(Agendar):
    """Mesmos campos de ``agendar`` + o agente dono (padrão: a Sora) e o fuso. Com
    ``seguinte_agente_id``, o resultado de cada execução segue para esse bot (Onda 3)."""

    agente_id: UUID | None = None
    fuso: str | None = None
    seguinte_agente_id: UUID | None = None
    seguinte_pedido: str | None = Field(default=None, max_length=MAX_PEDIDO_SEGUINTE)


class RotinaAtualizacao(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=120)
    pedido: str | None = Field(default=None, min_length=1, max_length=MAX_PEDIDO)
    silencioso: bool | None = None
    ativa: bool | None = None
    seguinte_agente_id: UUID | None = None
    """``null`` enviado de propósito tira o repasse; campo ausente não mexe."""
    seguinte_pedido: str | None = Field(default=None, max_length=MAX_PEDIDO_SEGUINTE)


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
    seguinte_agente_id: UUID | None = None
    seguinte_pedido: str | None = None


class ExecucaoSaida(BaseModel):
    id: UUID
    rotina_id: UUID
    iniciada_em: datetime
    concluida_em: datetime | None
    status: Literal["executando", "enviada", "silenciosa", "falhou"]
    origem: str = "agenda"
    resumo: str | None
    erro: str | None
    mensagem_id: UUID | None
    repasse_status: str | None = None
    repasse_erro: str | None = None
    repasse_mensagem_id: UUID | None = None


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
        seguinte_agente_id=rotina.seguinte_agente_id,
        seguinte_pedido=rotina.seguinte_pedido,
    )


async def _definir_seguinte(
    sessao: AsyncSession,
    usuario_id: UUID,
    rotina: Rotina,
    agente_id: UUID | None,
    pedido: str | None,
) -> None:
    """Liga ou tira o repasse. O bot que recebe é do mesmo usuário, existe e não é o dono."""
    if agente_id is None:
        rotina.seguinte_agente_id = None
        rotina.seguinte_pedido = None
        return
    if agente_id == rotina.agente_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Escolha outro bot: o resultado não volta para quem fez a rotina.",
        )
    existe = await sessao.scalar(
        select(Agente.id).where(
            Agente.id == agente_id,
            Agente.usuario_id == usuario_id,
            Agente.apagado_em.is_(None),
        )
    )
    if existe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot não encontrado.")
    texto = (pedido or "").strip()
    if not texto:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Diga o que o bot faz com o resultado."
        )
    if rotina.seguinte_agente_id != agente_id:
        rotina.seguinte_conversa_id = None  # outro bot: outra conversa
    rotina.seguinte_agente_id = agente_id
    rotina.seguinte_pedido = texto


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
async def listar_rotinas(
    usuario_id: UsuarioId, sessao: Sessao, agente_id: UUID | None = None
) -> list[RotinaSaida]:
    """Rotinas do usuário; com ``agente_id`` (o painel do bot), só as desse bot."""
    rotinas = await servico.listar(sessao, usuario_id, agente_id)
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
            args=Agendar.model_validate(
                dados.model_dump(
                    exclude={"agente_id", "fuso", "seguinte_agente_id", "seguinte_pedido"}
                )
            ),
            fuso=dados.fuso,
        )
    except ErroFerramenta as erro:
        codigo = 404 if "não encontrado" in str(erro) else 422
        raise HTTPException(codigo, str(erro)) from erro
    if dados.seguinte_agente_id is not None:
        await _definir_seguinte(
            sessao, usuario_id, rotina, dados.seguinte_agente_id, dados.seguinte_pedido
        )
        await sessao.flush()
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
    if "seguinte_agente_id" in dados.model_fields_set:
        await _definir_seguinte(
            sessao, usuario_id, rotina, dados.seguinte_agente_id, dados.seguinte_pedido
        )
    elif dados.seguinte_pedido is not None and rotina.seguinte_agente_id is not None:
        await _definir_seguinte(
            sessao, usuario_id, rotina, rotina.seguinte_agente_id, dados.seguinte_pedido
        )
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
    execucao = RotinaExecucao(
        id=uuid4(), rotina_id=rotina.id, usuario_id=usuario_id, origem="manual"
    )
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
