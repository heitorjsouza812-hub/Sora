"""Webhook das rotinas: a rota pública que recebe as chamadas e as rotas do dono para criar,
trocar o segredo, filtrar, pausar, testar e ver o histórico. Regras em
``app/rotinas/ganchos.py``."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis, usuario_atual
from app.modelos.tabelas import GanchoRotina, Rotina
from app.rotinas import ganchos, servico

roteador_publico = APIRouter(prefix="/ganchos", tags=["ganchos"])
roteador = APIRouter(prefix="/rotinas/{rotina_id}/gancho", tags=["rotinas"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]


class GanchoSaida(BaseModel):
    url: str
    ativo: bool
    tipos_evento: list[str]
    criado_em: datetime
    ultimo_recebido_em: datetime | None


class GanchoCriado(GanchoSaida):
    segredo: str
    """Mostrado só agora; depois, só trocando por outro."""


class GanchoCriacao(BaseModel):
    tipos_evento: list[str] | None = Field(default=None, max_length=ganchos.MAX_TIPOS_EVENTO)


class GanchoAtualizacao(BaseModel):
    ativo: bool | None = None
    tipos_evento: list[str] | None = Field(default=None, max_length=ganchos.MAX_TIPOS_EVENTO)


class EntregaSaida(BaseModel):
    id: UUID
    tipo_evento: str | None
    status: str
    tamanho: int
    execucao_id: UUID | None
    recebida_em: datetime


class RecebidaSaida(BaseModel):
    status: str
    execucao_id: UUID | None = None


def _url(requisicao: Request, gancho: GanchoRotina) -> str:
    base = (obter_configuracao().api_url or str(requisicao.base_url)).rstrip("/")
    return f"{base}/v1/ganchos/{gancho.rota}"


def _saida(requisicao: Request, gancho: GanchoRotina) -> GanchoSaida:
    return GanchoSaida(
        url=_url(requisicao, gancho),
        ativo=gancho.ativo,
        tipos_evento=list(gancho.tipos_evento or []),
        criado_em=gancho.criado_em,
        ultimo_recebido_em=gancho.ultimo_recebido_em,
    )


async def _rotina(sessao: AsyncSession, usuario_id: UUID, rotina_id: UUID) -> Rotina:
    rotina = await servico.obter(sessao, usuario_id, rotina_id)
    if rotina is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rotina não encontrada.")
    return rotina


async def _gancho(sessao: AsyncSession, usuario_id: UUID, rotina_id: UUID) -> GanchoRotina:
    rotina = await _rotina(sessao, usuario_id, rotina_id)
    gancho = await ganchos.gancho_da_rotina(sessao, rotina.id)
    if gancho is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esta rotina ainda não tem webhook.")
    return gancho


async def _rodar(rotina_id: UUID, execucao_id: UUID, corpo: bytes, tipo: str | None) -> None:
    from workers.fila import enfileirar

    await enfileirar(
        "executar_rotina",
        id_job=f"gancho:{execucao_id}",
        rotina_id=str(rotina_id),
        execucao_id=str(execucao_id),
        manual=True,
        dados_gancho=ganchos.dados_para_o_bot(corpo),
        tipo_evento=tipo,
    )


async def _ler_corpo(requisicao: Request) -> bytes:
    """Lê no máximo 256 KB + 1 byte: corpo maior é recusado sem ser lido inteiro."""
    partes: list[bytes] = []
    total = 0
    async for parte in requisicao.stream():
        total += len(parte)
        partes.append(parte)
        if total > ganchos.MAX_CORPO_BYTES:
            break
    return b"".join(partes)


@roteador_publico.post("/{rota}", response_model=RecebidaSaida)
async def receber_chamada(rota: str, requisicao: Request, sessao: Sessao, redis: RedisDep) -> Any:
    """Chamada de outro serviço (Standard Webhooks). Sem login: vale a assinatura."""
    corpo = await _ler_corpo(requisicao)
    cabecalhos = {k.lower(): v for k, v in requisicao.headers.items()}
    try:
        recebida, gancho = await ganchos.receber(sessao, redis, rota[:200], cabecalhos, corpo)
    except ganchos.ErroGancho as erro:
        extras = {"Retry-After": str(erro.espera)} if erro.espera else None
        return JSONResponse({"detail": erro.detalhe}, status_code=erro.status, headers=extras)
    await sessao.commit()
    if recebida.resultado == "aceita" and gancho is not None and recebida.execucao_id:
        await _rodar(gancho.rotina_id, recebida.execucao_id, corpo, ganchos.tipo_do_evento(corpo))
    codigo = status.HTTP_200_OK if recebida.resultado == "repetida" else status.HTTP_202_ACCEPTED
    return JSONResponse(
        RecebidaSaida(status=recebida.resultado, execucao_id=recebida.execucao_id).model_dump(
            mode="json"
        ),
        status_code=codigo,
    )


@roteador.get("")
async def obter_gancho(
    rotina_id: UUID, requisicao: Request, usuario_id: UsuarioId, sessao: Sessao
) -> GanchoSaida:
    return _saida(requisicao, await _gancho(sessao, usuario_id, rotina_id))


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def criar_gancho(
    rotina_id: UUID,
    dados: GanchoCriacao,
    requisicao: Request,
    usuario_id: UsuarioId,
    sessao: Sessao,
) -> GanchoCriado:
    """Liga o webhook da rotina ou troca o segredo (o antigo para de valer na hora)."""
    rotina = await _rotina(sessao, usuario_id, rotina_id)
    try:
        gancho, segredo = await ganchos.criar_ou_trocar_segredo(sessao, rotina, dados.tipos_evento)
    except ValueError as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro
    await sessao.refresh(gancho)
    return GanchoCriado(**_saida(requisicao, gancho).model_dump(), segredo=segredo)


@roteador.patch("")
async def atualizar_gancho(
    rotina_id: UUID,
    dados: GanchoAtualizacao,
    requisicao: Request,
    usuario_id: UsuarioId,
    sessao: Sessao,
) -> GanchoSaida:
    gancho = await _gancho(sessao, usuario_id, rotina_id)
    if dados.ativo is not None:
        gancho.ativo = dados.ativo
    if dados.tipos_evento is not None:
        try:
            gancho.tipos_evento = ganchos.normalizar_tipos(dados.tipos_evento)
        except ValueError as erro:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro
    await sessao.flush()
    return _saida(requisicao, gancho)


@roteador.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_gancho(rotina_id: UUID, usuario_id: UsuarioId, sessao: Sessao) -> None:
    await sessao.delete(await _gancho(sessao, usuario_id, rotina_id))


@roteador.post("/teste", status_code=status.HTTP_202_ACCEPTED)
async def testar_gancho(
    rotina_id: UUID, usuario_id: UsuarioId, sessao: Sessao, redis: RedisDep
) -> RecebidaSaida:
    """Assina e recebe uma chamada de teste pelo mesmo caminho de uma chamada de fora."""
    gancho = await _gancho(sessao, usuario_id, rotina_id)
    if not gancho.ativo:
        raise HTTPException(status.HTTP_409_CONFLICT, "O webhook está pausado.")
    tipo = gancho.tipos_evento[0] if gancho.tipos_evento else "sora.teste"
    corpo = json.dumps(
        {"type": tipo, "data": {"mensagem": "Chamada de teste enviada pela Sora."}},
        ensure_ascii=False,
    ).encode()
    mensagem_id, agora = f"teste_{uuid4().hex}", int(time.time())
    cabecalhos = {
        "webhook-id": mensagem_id,
        "webhook-timestamp": str(agora),
        "webhook-signature": ganchos.assinar(ganchos.segredo_de(gancho), mensagem_id, agora, corpo),
    }
    try:
        recebida, _ = await ganchos.receber(sessao, redis, gancho.rota, cabecalhos, corpo)
    except ganchos.ErroGancho as erro:
        raise HTTPException(erro.status, erro.detalhe) from erro
    await sessao.commit()
    if recebida.resultado == "aceita" and recebida.execucao_id:
        await _rodar(gancho.rotina_id, recebida.execucao_id, corpo, tipo)
    return RecebidaSaida(status=recebida.resultado, execucao_id=recebida.execucao_id)


@roteador.get("/entregas")
async def listar_entregas(
    rotina_id: UUID, usuario_id: UsuarioId, sessao: Sessao
) -> list[EntregaSaida]:
    gancho = await _gancho(sessao, usuario_id, rotina_id)
    return [
        EntregaSaida.model_validate(e, from_attributes=True)
        for e in await ganchos.entregas_recentes(sessao, gancho.id)
    ]
