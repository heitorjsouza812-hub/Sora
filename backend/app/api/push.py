"""Notificação no celular (Web Push): chave pública, inscrever/desinscrever o aparelho e teste.
Regras em ``app/push.py``."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app import push
from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.contas import ErroLimite
from app.core.dependencias import obter_redis, usuario_atual
from app.core.redis import verificar_limite

roteador = APIRouter(prefix="/push", tags=["push"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]
RedisDep = Annotated[Redis, Depends(obter_redis)]

LIMITE_TESTE = (5, 60 * 60)


class ChaveSaida(BaseModel):
    chave_publica: str | None
    """``None``: o servidor ainda não tem Web Push ligado."""


class DesinscricaoEntrada(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1_000)


class TesteSaida(BaseModel):
    enviadas: int


@roteador.get("/chave")
async def obter_chave(_usuario_id: UsuarioId) -> ChaveSaida:
    config = obter_configuracao()
    return ChaveSaida(chave_publica=config.vapid_chave_publica if config.push_ligado else None)


@roteador.post("/inscricoes", status_code=status.HTTP_201_CREATED)
async def inscrever(
    dados: push.InscricaoEntrada, requisicao: Request, usuario_id: UsuarioId, sessao: Sessao
) -> None:
    if not obter_configuracao().push_ligado:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "A notificação no celular ainda não está ligada neste servidor.",
        )
    aparelho = (requisicao.headers.get("user-agent") or "")[:200] or None
    try:
        await push.salvar_inscricao(sessao, usuario_id, dados, aparelho)
    except push.ErroInscricao as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro


@roteador.delete("/inscricoes", status_code=status.HTTP_204_NO_CONTENT)
async def desinscrever(dados: DesinscricaoEntrada, usuario_id: UsuarioId, sessao: Sessao) -> None:
    await push.apagar_inscricao(sessao, usuario_id, dados.endpoint)


@roteador.post("/teste")
async def testar(usuario_id: UsuarioId, sessao: Sessao, redis: RedisDep) -> TesteSaida:
    """Manda uma notificação de teste para os aparelhos da conta."""
    espera = await verificar_limite(redis, f"push:teste:{usuario_id}", *LIMITE_TESTE)
    if espera:
        raise ErroLimite(espera)
    envio = await push.enviar_para_usuario(
        sessao,
        usuario_id,
        {
            "titulo": "Sora",
            "corpo": "Pronto: este aparelho vai avisar quando um bot precisar de você.",
            "url": "/configuracoes?secao=notificacoes",
            "tag": "teste",
        },
    )
    return TesteSaida(enviadas=envio.enviadas)
