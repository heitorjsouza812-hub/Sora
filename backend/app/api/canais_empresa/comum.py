"""Roteadores, dependências e constantes compartilhados pelas rotas dos canais da empresa."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual

registro = logging.getLogger(__name__)

roteador = APIRouter(prefix="/canais-empresa", tags=["canais-empresa"])
roteador_webhooks = APIRouter(prefix="/canais-empresa/webhooks", tags=["canais-empresa"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
Usuario = Annotated[UUID, Depends(usuario_atual)]
RedisDep = Annotated[Redis, Depends(obter_redis)]

LIMITE_CORPO_WEBHOOK = 1_000_000
ATRASO_DO_RESUMO_SEGUNDOS = 60
