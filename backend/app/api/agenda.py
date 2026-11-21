"""Agenda das rotinas: execuções previstas e já feitas num intervalo, e o feed ``.ics``.

- ``GET /v1/agenda?de=…&ate=…``: previstas (das rotinas ativas) e feitas (``rotina_execucoes``).
- ``GET/POST/DELETE /v1/agenda/feed``: liga, troca ou desliga o endereço secreto do feed. O
  endereço só aparece ao ligar/trocar (no banco fica o hash).
- ``GET /v1/agenda/feed/{token}.ics``: o feed, sem login (o calendário não manda cabeçalho; o
  segredo está no endereço). Próximos 30 dias, só título e bot.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import seguranca
from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis, usuario_atual
from app.core.redis import verificar_limite
from app.modelos.tabelas import Agente, FeedAgenda, Rotina, RotinaExecucao
from app.rotinas import calendario

roteador = APIRouter(prefix="/agenda", tags=["rotinas"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]
RedisDep = Annotated[Redis, Depends(obter_redis)]

LIMITE_FEED = (60, 60 * 60)
"""Leituras do feed por hora (calendários costumam ler de hora em hora ou menos)."""


class OcorrenciaSaida(BaseModel):
    rotina_id: UUID
    agente_id: UUID
    titulo: str
    quando: datetime


class FeitaSaida(BaseModel):
    rotina_id: UUID
    titulo: str
    iniciada_em: datetime
    status: str
    origem: str


class AgendaSaida(BaseModel):
    previstas: list[OcorrenciaSaida]
    feitas: list[FeitaSaida]


class FeedSaida(BaseModel):
    ligado: bool
    criado_em: datetime | None = None
    url: str | None = None
    """Só na resposta de ligar/trocar."""


def _url_feed(requisicao: Request, token: str) -> str:
    base = (obter_configuracao().api_url or str(requisicao.base_url)).rstrip("/")
    return f"{base}/v1/agenda/feed/{token}.ics"


async def _rotinas(sessao: AsyncSession, usuario_id: UUID) -> list[Rotina]:
    return list(
        (
            await sessao.scalars(
                select(Rotina).where(Rotina.usuario_id == usuario_id, Rotina.ativa.is_(True))
            )
        ).all()
    )


@roteador.get("")
async def obter_agenda(
    usuario_id: UsuarioId,
    sessao: Sessao,
    de: Annotated[datetime, Query(description="Início (ISO 8601, com fuso).")],
    ate: Annotated[datetime, Query(description="Fim, exclusivo (no máximo 62 dias depois).")],
) -> AgendaSaida:
    de, ate = de.astimezone(UTC), ate.astimezone(UTC)
    agora = datetime.now(UTC)
    try:
        previstas = calendario.ocorrencias(await _rotinas(sessao, usuario_id), max(de, agora), ate)
    except ValueError as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from erro
    linhas = (
        await sessao.execute(
            select(RotinaExecucao, Rotina.titulo)
            .join(Rotina, Rotina.id == RotinaExecucao.rotina_id)
            .where(
                RotinaExecucao.usuario_id == usuario_id,
                RotinaExecucao.iniciada_em >= de,
                RotinaExecucao.iniciada_em < ate,
            )
            .order_by(RotinaExecucao.iniciada_em)
            .limit(1000)
        )
    ).all()
    return AgendaSaida(
        previstas=[OcorrenciaSaida(**o.__dict__) for o in previstas],
        feitas=[
            FeitaSaida(
                rotina_id=e.rotina_id,
                titulo=titulo,
                iniciada_em=e.iniciada_em,
                status=e.status,
                origem=e.origem,
            )
            for e, titulo in linhas
        ],
    )


@roteador.get("/feed")
async def obter_feed(usuario_id: UsuarioId, sessao: Sessao) -> FeedSaida:
    feed = await sessao.get(FeedAgenda, usuario_id)
    return FeedSaida(ligado=feed is not None, criado_em=feed.criado_em if feed else None)


@roteador.post("/feed", status_code=status.HTTP_201_CREATED)
async def ligar_feed(requisicao: Request, usuario_id: UsuarioId, sessao: Sessao) -> FeedSaida:
    """Liga o feed ou troca o endereço (o antigo para de funcionar na hora)."""
    token = secrets.token_urlsafe(32)
    feed = await sessao.get(FeedAgenda, usuario_id)
    if feed is None:
        feed = FeedAgenda(usuario_id=usuario_id, token_hash=seguranca.hash_token(token))
        sessao.add(feed)
    else:
        feed.token_hash = seguranca.hash_token(token)
        feed.criado_em = datetime.now(UTC)
    await sessao.flush()
    await sessao.refresh(feed)
    return FeedSaida(ligado=True, criado_em=feed.criado_em, url=_url_feed(requisicao, token))


@roteador.delete("/feed", status_code=status.HTTP_204_NO_CONTENT)
async def desligar_feed(usuario_id: UsuarioId, sessao: Sessao) -> None:
    await sessao.execute(delete(FeedAgenda).where(FeedAgenda.usuario_id == usuario_id))


@roteador.get("/feed/{arquivo}", response_class=Response)
async def baixar_feed(arquivo: str, sessao: Sessao, redis: RedisDep) -> Response:
    """O feed ``.ics`` (sem login: o segredo é o endereço)."""
    token = arquivo.removesuffix(".ics")
    if not arquivo.endswith(".ics") or not token or len(token) > 100:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feed não encontrado.")
    token_hash = seguranca.hash_token(token)
    feed = await sessao.scalar(select(FeedAgenda).where(FeedAgenda.token_hash == token_hash))
    if feed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feed não encontrado.")
    espera = await verificar_limite(redis, f"agenda:feed:{token_hash}", *LIMITE_FEED)
    if espera:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Muitas leituras do feed.",
            headers={"Retry-After": str(espera)},
        )
    agora = datetime.now(UTC)
    previstas = calendario.ocorrencias(
        await _rotinas(sessao, feed.usuario_id),
        agora,
        agora + calendario.FEED_FUTURO,
    )
    nomes = dict(
        (
            await sessao.execute(
                select(Agente.id, Agente.nome).where(Agente.usuario_id == feed.usuario_id)
            )
        ).all()
    )
    corpo = calendario.gerar_ics([(o, nomes.get(o.agente_id, "Sora")) for o in previstas], agora)
    return Response(
        corpo,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Cache-Control": "private, max-age=900",
            "Content-Disposition": 'inline; filename="rotinas-sora.ics"',
        },
    )
