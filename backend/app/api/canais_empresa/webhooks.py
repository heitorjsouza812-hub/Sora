"""Webhooks do Slack e da Meta: sem login, a origem é conferida pela assinatura
(``X-Slack-Signature``; ``X-Hub-Signature-256`` e o handshake do GET na Meta)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.canais_empresa.comum import (
    ATRASO_DO_RESUMO_SEGUNDOS,
    LIMITE_CORPO_WEBHOOK,
    Sessao,
    registro,
    roteador_webhooks,
)
from app.canais_empresa import conexoes, ingestao
from app.canais_empresa.assinaturas import handshake_meta_valido, meta_autentico, slack_autentico
from app.canais_empresa.tabelas import (
    ConexaoCanalEmpresa,
)


async def _corpo_limitado(requisicao: Request) -> bytes:
    """Lê o corpo no fluxo e para em ``LIMITE_CORPO_WEBHOOK`` (413), com ou sem
    ``Content-Length`` (``Transfer-Encoding: chunked`` não tem): nunca guarda mais que o teto."""
    declarado = requisicao.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > LIMITE_CORPO_WEBHOOK:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE)
    pedacos: list[bytes] = []
    total = 0
    async for pedaco in requisicao.stream():
        total += len(pedaco)
        if total > LIMITE_CORPO_WEBHOOK:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE)
        pedacos.append(pedaco)
    return b"".join(pedacos)


async def _conexao_do_webhook(
    sessao: AsyncSession, conexao_id: UUID, canal: str
) -> ConexaoCanalEmpresa:
    c = await sessao.get(ConexaoCanalEmpresa, conexao_id)
    if c is None or c.canal != canal or not c.ativa:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return c


async def _enfileirar_resumo(usuario_id: UUID) -> None:
    """Põe o resumo na fila (adiado, para juntar as mensagens de uma mesma conversa). Se a fila
    falhar nada se perde: as mensagens já estão no banco e a rotina do worker as pega."""
    try:
        from workers.fila import enfileirar

        agora = datetime.now(UTC)
        await enfileirar(
            "processar_canais_empresa",
            id_job=f"ce:{usuario_id}:{int(time.time() // 60)}",
            agendar_para=agora + timedelta(seconds=ATRASO_DO_RESUMO_SEGUNDOS),
            usuario_id=str(usuario_id),
        )
    except Exception:
        registro.warning("não consegui enfileirar o resumo dos canais da empresa", exc_info=True)


async def _guardar(
    sessao: AsyncSession, c: ConexaoCanalEmpresa, mensagens: list[ingestao.MensagemNormalizada]
) -> int:
    novas = await ingestao.registrar_mensagens(sessao, c, mensagens)
    if novas:
        await sessao.commit()
        await _enfileirar_resumo(c.usuario_id)
    return len(novas)


@roteador_webhooks.post("/slack/{conexao_id}", include_in_schema=False)
async def webhook_slack(
    conexao_id: UUID,
    requisicao: Request,
    sessao: Sessao,
    timestamp: Annotated[str | None, Header(alias="X-Slack-Request-Timestamp")] = None,
    assinatura: Annotated[str | None, Header(alias="X-Slack-Signature")] = None,
) -> Response:
    corpo = await _corpo_limitado(requisicao)
    c = await _conexao_do_webhook(sessao, conexao_id, "slack")
    segredos = conexoes.decifrar_segredos(c)
    if not slack_autentico(segredos.get("signing_secret", ""), corpo, timestamp, assinatura):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Assinatura inválida.")
    try:
        carga = json.loads(corpo)
    except ValueError as erro:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON inválido.") from erro
    if not isinstance(carga, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON inválido.")
    if carga.get("type") == "url_verification" and isinstance(carga.get("challenge"), str):
        return Response(
            json.dumps({"challenge": carga["challenge"]}), media_type="application/json"
        )
    await _guardar(sessao, c, ingestao.normalizar_slack(carga, c.config, c.canais_escolhidos))
    return Response(json.dumps({"ok": True}), media_type="application/json")


@roteador_webhooks.get("/whatsapp/{conexao_id}", include_in_schema=False)
async def verificar_whatsapp(
    conexao_id: UUID,
    sessao: Sessao,
    modo: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    desafio: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    """Handshake da Meta ao cadastrar o webhook: devolve ``hub.challenge`` em texto puro."""
    c = await _conexao_do_webhook(sessao, conexao_id, "whatsapp")
    segredos = conexoes.decifrar_segredos(c)
    if not handshake_meta_valido(segredos.get("verify_token", ""), modo, token) or desafio is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    return Response(desafio, media_type="text/plain")


@roteador_webhooks.post("/whatsapp/{conexao_id}", include_in_schema=False)
async def webhook_whatsapp(
    conexao_id: UUID,
    requisicao: Request,
    sessao: Sessao,
    assinatura: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> Response:
    corpo = await _corpo_limitado(requisicao)
    c = await _conexao_do_webhook(sessao, conexao_id, "whatsapp")
    segredos = conexoes.decifrar_segredos(c)
    if not meta_autentico(segredos.get("app_secret", ""), corpo, assinatura):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Assinatura inválida.")
    try:
        carga = json.loads(corpo)
    except ValueError as erro:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON inválido.") from erro
    if isinstance(carga, dict):
        await _guardar(sessao, c, ingestao.normalizar_whatsapp(carga, c.canais_escolhidos))
    return Response(json.dumps({"ok": True}), media_type="application/json")
