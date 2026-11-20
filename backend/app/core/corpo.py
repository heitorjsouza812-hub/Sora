"""Teto do corpo das requisições, antes de qualquer rota; especificação §8.3.

O FastAPI/Starlette grava o multipart inteiro (no ``/tmp``) ANTES de a rota de anexos conferir os
20 MB. No contêiner o ``/tmp`` é um tmpfs de 64 MB: um envio grande enchia o tmpfs e derrubava os
outros envios. Aqui o corpo é contado enquanto chega e passa de ``MAX_CORPO_BYTES`` vira 413.
O Caddy (``infra/Caddyfile``) tem o mesmo teto na frente; este vale também sem o proxy.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_CORPO_BYTES = 25 * 1024 * 1024
"""Anexo e áudio aceitam até 20 MB; a folga é do envelope multipart."""

MENSAGEM = "O envio passa do limite de 25 MB."


class LimiteDeCorpo:
    """Middleware ASGI: recusa com 413 corpo declarado ou recebido acima do teto."""

    def __init__(self, app: ASGIApp, maximo: int = MAX_CORPO_BYTES) -> None:
        self.app = app
        self.maximo = maximo

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declarado = _content_length(scope)
        if declarado is not None and declarado > self.maximo:
            await _responder_413(send)
            return
        recebido = 0

        async def receber() -> Message:
            nonlocal recebido
            mensagem = await receive()
            if mensagem["type"] == "http.request":
                recebido += len(mensagem.get("body", b""))
                if recebido > self.maximo:
                    # HTTPException atravessa o parser do corpo do FastAPI (ele relança
                    # HTTPException) e vira a resposta 413 no ExceptionMiddleware.
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, MENSAGEM)
            return mensagem

        await self.app(scope, receber, send)


def _content_length(scope: Scope) -> int | None:
    for nome, valor in scope.get("headers", []):
        if nome == b"content-length":
            texto = valor.decode("latin-1").strip()
            return int(texto) if texto.isdigit() else None
    return None


async def _responder_413(send: Send) -> None:
    corpo = json.dumps({"detail": MENSAGEM}).encode()
    cabecalhos: list[Any] = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(corpo)).encode()),
        (b"connection", b"close"),
    ]
    await send({"type": "http.response.start", "status": 413, "headers": cabecalhos})
    await send({"type": "http.response.body", "body": corpo})
