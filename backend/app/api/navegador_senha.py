"""Senha segura no navegador do bot: o app manda a senha do cartão "Senha de <site>" por aqui.

A senha vai cifrada para o Redis por 5 minutos (``app/navegador/senha_segura.py``) e o cartão é
decidido como "permitir" pelo mesmo caminho das outras aprovações (``/v1/aprovacoes/.../decidir``),
que retoma o turno do bot. O valor nunca é gravado no banco nem devolvido.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.contas import ErroLimite
from app.core.dependencias import obter_redis, usuario_atual
from app.core.redis import verificar_limite
from app.modelos.enumeracoes import StatusAprovacao
from app.modelos.tabelas import Aprovacao
from app.navegador import senha_segura

roteador = APIRouter(prefix="/navegador/senhas", tags=["navegador"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]
RedisDep = Annotated[Redis, Depends(obter_redis)]

LIMITE_ENVIOS = (10, 15 * 60)


class SenhaEntrada(BaseModel):
    senha: SecretStr = Field(min_length=1, max_length=senha_segura.MAX_SENHA)


@roteador.post("/{cartao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def enviar_senha(
    cartao_id: UUID,
    dados: SenhaEntrada,
    usuario_id: UsuarioId,
    sessao: Sessao,
    redis: RedisDep,
) -> None:
    from app.api.aprovacoes import decidir_aprovacao
    from app.modelos.enumeracoes import DecisaoAprovacao
    from app.modelos.esquemas import DecisaoAprovacaoEntrada

    espera = await verificar_limite(redis, f"navegador:senha:envios:{usuario_id}", *LIMITE_ENVIOS)
    if espera:
        raise ErroLimite(espera)
    cartao = await sessao.scalar(
        select(Aprovacao).where(Aprovacao.id == cartao_id, Aprovacao.usuario_id == usuario_id)
    )
    acao = cartao.acao if cartao is not None and isinstance(cartao.acao, dict) else {}
    if cartao is None or acao.get("tipo") != "preencher_senha":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido de senha não encontrado.")
    if cartao.status != StatusAprovacao.PENDENTE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este pedido não está mais pendente.")
    await senha_segura.guardar(redis, usuario_id, cartao_id, dados.senha.get_secret_value())
    try:
        await decidir_aprovacao(
            cartao_id,
            DecisaoAprovacaoEntrada(decisao=DecisaoAprovacao.PERMITIR_UMA_VEZ),
            usuario_id,
            sessao,
            redis,
            ArqRedis(redis.connection_pool),
        )
    except BaseException:
        await senha_segura.apagar(redis, cartao_id)  # não decidiu: a senha não fica esperando
        raise
