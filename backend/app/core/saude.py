"""Prontidão da API (``/health/pronto``): banco e Redis respondem?; especificação §8.3.

``/health`` continua só dizendo que o processo está vivo. Esta rota é para o healthcheck do
Compose e para um balanceador: com o banco ou o Redis fora, a API sobe mas não atende ninguém.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

registro = logging.getLogger(__name__)

PRAZO_S = 3.0


async def _banco_ok() -> bool:
    from app.core.banco import fabrica_sessoes

    async with fabrica_sessoes()() as sessao:
        return (await sessao.scalar(text("select 1"))) == 1


async def _redis_ok(app: FastAPI) -> bool:
    redis = getattr(app.state, "redis", None)
    return redis is not None and bool(await redis.ping())


async def _conferir(nome: str, verificacao) -> bool:
    try:
        return await asyncio.wait_for(verificacao, PRAZO_S)
    except Exception:  # timeout, conexão recusada, senha errada…
        registro.warning("prontidão: %s não respondeu", nome, exc_info=True)
        return False


async def verificar_prontidao(app: FastAPI) -> JSONResponse:
    banco, redis = await asyncio.gather(
        _conferir("banco", _banco_ok()), _conferir("redis", _redis_ok(app))
    )
    corpo = {
        "status": "ok" if banco and redis else "indisponivel",
        "banco": "ok" if banco else "falhou",
        "redis": "ok" if redis else "falhou",
    }
    return JSONResponse(corpo, status_code=200 if banco and redis else 503)
