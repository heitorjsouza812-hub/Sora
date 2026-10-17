"""Rotas dos canais de mensagem (fase 3): webhook do Telegram e vínculo da conta.

Veja ``app/canais/telegram.py``. O webhook não usa login: a origem é conferida pelo segredo
do cabeçalho ``X-Telegram-Bot-Api-Secret-Token``. Ele sempre responde 200 ao Telegram
(senão o Telegram repete a mesma atualização), exceto quando o segredo não confere (401).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from redis.asyncio import Redis

from app.canais.telegram import (
    CABECALHO_SEGREDO,
    VALIDADE_CODIGO_SEGUNDOS,
    ClienteTelegram,
    ErroTelegram,
    codigo_do_start,
    criar_codigo_vinculo,
    ler_atualizacao,
    usar_codigo_vinculo,
    webhook_autentico,
)
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis, usuario_atual

roteador = APIRouter(prefix="/canais", tags=["canais"])

TEXTO_SEM_VINCULO = (
    "Oi! Para falar com a Sora por aqui, abra o app, vá em Configurações → Canais → Telegram "
    "e mande para mim o comando /start com o código que aparecer."
)
TEXTO_VINCULADO = "Pronto! Agora é só mandar mensagem que a Sora responde por aqui."
TEXTO_CODIGO_INVALIDO = "Esse código não vale mais. Gere outro no app da Sora."


class VinculoSaida(BaseModel):
    codigo: str
    expira_em_segundos: int
    comando: str


def _segredos() -> tuple[str, str]:
    config = obter_configuracao()
    token = config.telegram_token_bot.get_secret_value() if config.telegram_token_bot else ""
    segredo = (
        config.telegram_segredo_webhook.get_secret_value()
        if config.telegram_segredo_webhook
        else ""
    )
    return token, segredo


@roteador.post("/telegram/vinculo", status_code=status.HTTP_201_CREATED)
async def criar_vinculo_telegram(
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    redis: Annotated[Redis, Depends(obter_redis)],
) -> VinculoSaida:
    """Gera o código de uso único para ligar o Telegram à conta."""
    token, segredo = _segredos()
    if not token or not segredo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "O canal Telegram não está ligado.")
    codigo = await criar_codigo_vinculo(redis, usuario_id)
    return VinculoSaida(
        codigo=codigo, expira_em_segundos=VALIDADE_CODIGO_SEGUNDOS, comando=f"/start {codigo}"
    )


async def _vincular(usuario_id: UUID, chat_id: str) -> None:
    """Grava ``canais_vinculados`` (troca o dono se o chat já estava ligado a outra conta)."""
    from sqlalchemy.dialects.postgresql import insert

    from app.core.banco import fabrica_sessoes
    from app.modelos.tabelas import CanalVinculado

    async with fabrica_sessoes()() as sessao:
        comando = insert(CanalVinculado).values(
            usuario_id=usuario_id, canal="telegram", chat_id=chat_id
        )
        comando = comando.on_conflict_do_update(
            index_elements=["canal", "chat_id"], set_={"usuario_id": usuario_id}
        )
        await sessao.execute(comando)
        await sessao.commit()


async def _dono_do_chat(chat_id: str) -> UUID | None:
    from sqlalchemy import select

    from app.core.banco import fabrica_sessoes
    from app.modelos.tabelas import CanalVinculado

    async with fabrica_sessoes()() as sessao:
        return await sessao.scalar(
            select(CanalVinculado.usuario_id).where(
                CanalVinculado.canal == "telegram", CanalVinculado.chat_id == chat_id
            )
        )


@roteador.post("/telegram/webhook", include_in_schema=False)
async def webhook_telegram(
    corpo: dict[str, Any],
    redis: Annotated[Redis, Depends(obter_redis)],
    segredo_recebido: Annotated[str | None, Header(alias=CABECALHO_SEGREDO)] = None,
) -> dict[str, bool]:
    token, segredo = _segredos()
    if not token or not segredo:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not webhook_autentico(segredo_recebido, segredo):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    mensagem = ler_atualizacao(corpo)
    if mensagem is None:
        return {"ok": True}
    cliente = ClienteTelegram(token)
    try:
        if mensagem.texto.startswith("/start"):
            codigo = codigo_do_start(mensagem.texto)
            usuario_id = await usar_codigo_vinculo(redis, codigo) if codigo else None
            if usuario_id is None:
                await cliente.enviar(
                    mensagem.chat_id, TEXTO_SEM_VINCULO if not codigo else TEXTO_CODIGO_INVALIDO
                )
                return {"ok": True}
            await _vincular(usuario_id, mensagem.chat_id)
            await cliente.enviar(mensagem.chat_id, TEXTO_VINCULADO)
            return {"ok": True}
        dono = await _dono_do_chat(mensagem.chat_id)
        if dono is None:
            await cliente.enviar(mensagem.chat_id, TEXTO_SEM_VINCULO)
            return {"ok": True}
        from workers.fila import enfileirar

        await cliente.digitando(mensagem.chat_id)
        await enfileirar(
            "responder_canal",
            id_job=f"telegram:{mensagem.chat_id}:{mensagem.mensagem_id}",
            usuario_id=str(dono),
            canal="telegram",
            chat_id=mensagem.chat_id,
            texto=mensagem.texto,
        )
    except ErroTelegram:
        # O Telegram não deve repetir a atualização por causa de uma falha nossa de envio.
        return {"ok": True}
    return {"ok": True}
