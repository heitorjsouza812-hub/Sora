"""Rotas do computador do bot para o app (Farol, C2; ``docs/computador-por-bot.md``).

- ``GET  /v1/agentes/{id}/computador``: estado (ligado, alvo, tamanho, janela ativa, última ação);
- ``GET  /v1/agentes/{id}/computador/captura``: última captura PNG em tamanho cheio;
- ``POST /v1/agentes/{id}/computador/desligar``: pede ao worker para desligar.

Só o dono do bot vê ou mexe (bot apagado ou de outra conta = 404). A captura fica no Redis por
uma hora; a tela ao vivo chega pelo evento ``computador.tela`` de ``GET /v1/eventos``.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.computador.servico import CHAVE_CAPTURA, CHAVE_ESTADO
from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis, usuario_atual
from app.modelos.tabelas import Agente

roteador = APIRouter(prefix="/agentes", tags=["computador"])
Usuario = Annotated[UUID, Depends(usuario_atual)]
Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]


class ComputadorEstado(BaseModel):
    agente_id: UUID
    disponivel: bool
    """O servidor oferece computador virtual (sandbox ligado)."""
    ligado: bool
    alvo: Literal["virtual", "pc_usuario"] = "virtual"
    largura: int | None = None
    altura: int | None = None
    janela_ativa: str | None = None
    acao: str | None = None
    atualizado_em: datetime | None = None


async def _conferir_dono(sessao: AsyncSession, usuario_id: UUID, agente_id: UUID) -> None:
    existe = await sessao.scalar(
        select(Agente.id).where(
            Agente.id == agente_id, Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None)
        )
    )
    if existe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot não encontrado.")


@roteador.get("/{agente_id}/computador")
async def estado_do_computador(
    agente_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> ComputadorEstado:
    await _conferir_dono(sessao, usuario_id, agente_id)
    disponivel = obter_configuracao().sandbox_ativo
    bruto = await redis.get(CHAVE_ESTADO.format(agente_id=agente_id))
    if not bruto:
        return ComputadorEstado(agente_id=agente_id, disponivel=disponivel, ligado=False)
    dados = json.loads(bruto)
    return ComputadorEstado(
        agente_id=agente_id,
        disponivel=disponivel,
        ligado=bool(dados.get("ligado")),
        alvo=dados.get("alvo") or "virtual",
        largura=dados.get("largura"),
        altura=dados.get("altura"),
        janela_ativa=dados.get("janela_ativa"),
        acao=dados.get("acao"),
        atualizado_em=dados.get("atualizado_em"),
    )


@roteador.get(
    "/{agente_id}/computador/captura",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def captura_do_computador(
    agente_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> Response:
    await _conferir_dono(sessao, usuario_id, agente_id)
    guardada = await redis.get(CHAVE_CAPTURA.format(agente_id=agente_id))
    if not guardada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ainda não há captura deste computador.")
    return Response(
        base64.b64decode(guardada),
        media_type="image/png",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@roteador.post("/{agente_id}/computador/desligar", status_code=status.HTTP_202_ACCEPTED)
async def desligar_o_computador(
    agente_id: UUID, usuario_id: Usuario, sessao: Sessao
) -> dict[str, bool]:
    await _conferir_dono(sessao, usuario_id, agente_id)
    from workers.fila import obter_fila

    fila = await obter_fila()
    await fila.enqueue_job(
        "desligar_computador",
        str(usuario_id),
        str(agente_id),
    )
    return {"pedido": True}
