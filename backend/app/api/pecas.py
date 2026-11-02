"""Rotas das peças do Rakazo para Configurações e para o chat (Âncora, etapa 4): memória,
pendências e o medidor de contexto. Contrato em ``.maestri/contrato-etapa4.md``.

Tudo é do dono: registro de outro usuário responde 404 como se não existisse. Apagar uma
memória pelo usuário não pede cartão (o cartão existe para o agente pedir, não para o dono).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.eventos.equipe import ContextoAtualizado
from app.ferramentas.base import ErroFerramenta
from app.memoria.servico import MAX_CONTEUDO, ArmazemMemoriasSQL, ServicoMemoria
from app.modelos.tabelas import Agente, Conversa, Memoria
from app.modelos.tabelas import Pendencia as LinhaPendencia
from app.pendencias import MAX_NOTAS, MAX_PENDENCIAS_ABERTAS, MAX_TITULO, STATUS_ABERTOS

roteador = APIRouter(tags=["memoria-e-contexto"], dependencies=[Depends(usuario_atual)])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
Usuario = Annotated[UUID, Depends(usuario_atual)]
RedisDep = Annotated[Redis, Depends(obter_redis)]


# ---------------------------------------------------------------- memória


class MemoriaSaida(BaseModel):
    id: UUID
    agente_id: UUID | None
    conteudo: str
    tipo: str
    origem: str
    travada: bool
    criada_em: datetime


class MemoriaEntrada(BaseModel):
    conteudo: str = Field(min_length=1, max_length=MAX_CONTEUDO)
    agente_id: UUID | None = None


def _memoria(linha: Memoria) -> MemoriaSaida:
    return MemoriaSaida(
        id=linha.id,
        agente_id=linha.agente_id,
        conteudo=linha.conteudo,
        tipo=str(getattr(linha.tipo, "value", linha.tipo)),
        origem=str(getattr(linha.origem, "value", linha.origem)),
        travada=linha.travada,
        criada_em=linha.criada_em,
    )


async def _exigir_agente(sessao: AsyncSession, usuario_id: UUID, agente_id: UUID) -> None:
    achou = await sessao.scalar(
        select(Agente.id).where(
            Agente.id == agente_id, Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None)
        )
    )
    if achou is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente não encontrado.")


@roteador.get("/memorias")
async def listar_memorias(
    usuario_id: Usuario, sessao: Sessao, agente_id: UUID | None = None
) -> list[MemoriaSaida]:
    consulta = select(Memoria).where(Memoria.usuario_id == usuario_id, Memoria.apagada_em.is_(None))
    if agente_id is not None:
        await _exigir_agente(sessao, usuario_id, agente_id)
        consulta = consulta.where((Memoria.agente_id.is_(None)) | (Memoria.agente_id == agente_id))
    linhas = await sessao.scalars(consulta.order_by(Memoria.criada_em.desc()).limit(500))
    return [_memoria(linha) for linha in linhas]


@roteador.post("/memorias", status_code=status.HTTP_201_CREATED)
async def criar_memoria(
    dados: MemoriaEntrada, usuario_id: Usuario, sessao: Sessao, resposta: Response
) -> MemoriaSaida:
    if dados.agente_id is not None:
        await _exigir_agente(sessao, usuario_id, dados.agente_id)
    from app.memoria.vetorizador import vetorizador_do_usuario

    servico = ServicoMemoria(
        ArmazemMemoriasSQL(sessao), await vetorizador_do_usuario(sessao, usuario_id)
    )
    existentes = {r.id for r in await servico.armazem.listar(usuario_id, dados.agente_id)}
    try:
        registro = await servico.lembrar(usuario_id, dados.agente_id, dados.conteudo)
    except ErroFerramenta as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro
    if registro.id in existentes:
        resposta.status_code = status.HTTP_200_OK
    linha = await sessao.get(Memoria, registro.id)
    await sessao.commit()
    return _memoria(linha)


@roteador.delete("/memorias/{memoria_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_memoria(memoria_id: UUID, usuario_id: Usuario, sessao: Sessao) -> None:
    servico = ServicoMemoria(ArmazemMemoriasSQL(sessao))
    if not await servico.esquecer(usuario_id, memoria_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memória não encontrada.")
    await sessao.commit()


# ---------------------------------------------------------------- pendências

StatusPendencia = Literal["aberta", "estacionada", "concluida"]


class PendenciaSaida(BaseModel):
    id: UUID
    agente_id: UUID
    titulo: str
    notas: str
    status: str
    criada_em: datetime
    atualizada_em: datetime


class PendenciaEntrada(BaseModel):
    titulo: str = Field(min_length=1, max_length=MAX_TITULO)
    notas: str = Field(default="", max_length=MAX_NOTAS)
    status: Literal["aberta", "estacionada"] = "aberta"


class PendenciaAlteracao(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=MAX_TITULO)
    notas: str | None = Field(default=None, max_length=MAX_NOTAS)
    status: StatusPendencia | None = None


def _pendencia(linha: LinhaPendencia) -> PendenciaSaida:
    return PendenciaSaida(
        id=linha.id,
        agente_id=linha.agente_id,
        titulo=linha.titulo,
        notas=linha.notas,
        status=linha.status,
        criada_em=linha.criada_em,
        atualizada_em=linha.atualizada_em,
    )


@roteador.get("/agentes/{agente_id}/pendencias")
async def listar_pendencias(
    agente_id: UUID, usuario_id: Usuario, sessao: Sessao, incluir_concluidas: bool = False
) -> list[PendenciaSaida]:
    await _exigir_agente(sessao, usuario_id, agente_id)
    consulta = select(LinhaPendencia).where(
        LinhaPendencia.usuario_id == usuario_id, LinhaPendencia.agente_id == agente_id
    )
    if not incluir_concluidas:
        consulta = consulta.where(LinhaPendencia.status.in_(STATUS_ABERTOS))
    linhas = await sessao.scalars(consulta.order_by(LinhaPendencia.atualizada_em.desc()))
    return [_pendencia(linha) for linha in linhas]


@roteador.post("/agentes/{agente_id}/pendencias", status_code=status.HTTP_201_CREATED)
async def criar_pendencia(
    agente_id: UUID, dados: PendenciaEntrada, usuario_id: Usuario, sessao: Sessao
) -> PendenciaSaida:
    await _exigir_agente(sessao, usuario_id, agente_id)
    abertas = await sessao.scalar(
        select(func.count())
        .select_from(LinhaPendencia)
        .where(
            LinhaPendencia.usuario_id == usuario_id,
            LinhaPendencia.agente_id == agente_id,
            LinhaPendencia.status.in_(STATUS_ABERTOS),
        )
    )
    if (abertas or 0) >= MAX_PENDENCIAS_ABERTAS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Muitas pendências abertas.")
    linha = LinhaPendencia(
        id=uuid4(),
        usuario_id=usuario_id,
        agente_id=agente_id,
        titulo=dados.titulo.strip(),
        notas=dados.notas.strip(),
        status=dados.status,
    )
    sessao.add(linha)
    await sessao.commit()
    await sessao.refresh(linha)
    return _pendencia(linha)


async def _pendencia_do_dono(
    sessao: AsyncSession, usuario_id: UUID, pendencia_id: UUID
) -> LinhaPendencia:
    linha = await sessao.scalar(
        select(LinhaPendencia).where(
            LinhaPendencia.id == pendencia_id, LinhaPendencia.usuario_id == usuario_id
        )
    )
    if linha is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pendência não encontrada.")
    return linha


@roteador.patch("/pendencias/{pendencia_id}")
async def alterar_pendencia(
    pendencia_id: UUID, dados: PendenciaAlteracao, usuario_id: Usuario, sessao: Sessao
) -> PendenciaSaida:
    linha = await _pendencia_do_dono(sessao, usuario_id, pendencia_id)
    if dados.titulo is not None:
        linha.titulo = dados.titulo.strip()
    if dados.notas is not None:
        linha.notas = dados.notas.strip()
    if dados.status is not None:
        linha.status = dados.status
    linha.atualizada_em = func.now()
    await sessao.commit()
    await sessao.refresh(linha)
    return _pendencia(linha)


@roteador.delete("/pendencias/{pendencia_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_pendencia(pendencia_id: UUID, usuario_id: Usuario, sessao: Sessao) -> None:
    linha = await _pendencia_do_dono(sessao, usuario_id, pendencia_id)
    await sessao.delete(linha)
    await sessao.commit()


# ---------------------------------------------------------------- medidor de contexto


@roteador.get("/agentes/{agente_id}/contexto")
async def contexto_do_agente(
    agente_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> list[ContextoAtualizado]:
    from app.contexto.estado import evento_de, ler_todos

    await _exigir_agente(sessao, usuario_id, agente_id)
    return [evento_de(estado) for estado in await ler_todos(redis, agente_id)]


@roteador.post("/agentes/{agente_id}/contexto/compactar", status_code=status.HTTP_202_ACCEPTED)
async def compactar_agora(
    agente_id: UUID,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
    fio: str = "principal",
) -> ContextoAtualizado:
    """Botão "Compactar agora". 409 com o motivo se o agente estiver trabalhando."""
    from app.contexto import SituacaoCompactacao, medir, pedir_compactacao_manual
    from app.contexto.estado import evento_de, ler, registrar_e_publicar, turno_rodando
    from workers.fila import enfileirar

    await _exigir_agente(sessao, usuario_id, agente_id)
    conversa_id = await sessao.scalar(
        select(Conversa.id)
        .where(Conversa.usuario_id == usuario_id, Conversa.agente_id == agente_id)
        .order_by(Conversa.atualizada_em.desc())
        .limit(1)
    )
    if conversa_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este agente ainda não tem conversa.")
    estado = await ler(redis, agente_id, fio) or medir(
        agente_id, fio, janela=None, tokens_informados=0
    )
    decisao = pedir_compactacao_manual(
        estado, turno_rodando=await turno_rodando(redis, agente_id), itens_na_fila=0
    )
    if decisao.decisao == "recusar":
        raise HTTPException(status.HTTP_409_CONFLICT, decisao.motivo)
    from dataclasses import replace

    novo = await registrar_e_publicar(
        redis,
        replace(estado, compactacao=SituacaoCompactacao.COMPACTANDO),
        usuario_id=usuario_id,
        conversa_id=conversa_id,
    )
    await enfileirar(
        "compactar_historico",
        conversa_id=str(conversa_id),
        agente_id=str(agente_id),
        fio=fio,
    )
    return evento_de(novo)
