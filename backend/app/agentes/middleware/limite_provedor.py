"""Espera o limite por minuto do provedor e enxuga o pedido grande demais (Âncora, rodada 4).

Fica por dentro da nova tentativa e da troca de modelo (ver ``montar_middleware``): um 429 com
``retry-after`` espera e repete o MESMO modelo; "Request too large" repete com o pedido mais
curto; se nada resolver, sobe ``ErroLimiteDoProvedor`` (que não provoca troca de modelo).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langgraph.errors import GraphBubbleUp

from app.llm.limite import (
    TENTATIVAS_NO_LIMITE,
    ErroLimiteDoProvedor,
    enxugar,
    espera_com_teto,
    pedido_grande_demais,
)
from app.llm.troca import MotivoTroca, classificar_erro

registro = logging.getLogger(__name__)

AoEsperar = Callable[[int], Awaitable[None]]
Dormir = Callable[[float], Awaitable[None]]


class MiddlewareLimiteDoProvedor(AgentMiddleware):
    def __init__(
        self, *, ao_esperar: AoEsperar | None = None, dormir: Dormir | None = None
    ) -> None:
        self._ao_esperar = ao_esperar
        self._dormir = dormir or asyncio.sleep

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Any:
        # Resultados antigos do navegador já entram resumidos: a árvore velha não serve mais.
        pedido = request.override(messages=enxugar(list(request.messages), 1))
        espera_feita = 0
        nivel = 1
        while True:
            try:
                return await handler(pedido)
            except GraphBubbleUp:
                raise
            except Exception as erro:
                if classificar_erro(erro) is not MotivoTroca.LIMITE_DE_TAXA:
                    raise
                if pedido_grande_demais(erro):
                    if nivel >= 2:
                        raise ErroLimiteDoProvedor("pedido grande demais") from None
                    nivel = 2
                    registro.warning("pedido grande demais para o plano; enxugando e repetindo")
                    pedido = request.override(messages=enxugar(list(request.messages), 2))
                    continue
                espera = espera_com_teto(erro)
                if espera is None or espera_feita >= TENTATIVAS_NO_LIMITE:
                    raise ErroLimiteDoProvedor("limite por minuto") from None
                espera_feita += 1
                registro.warning("limite do provedor; esperando %.1f s", espera)
                if self._ao_esperar is not None:
                    try:
                        await self._ao_esperar(round(espera))
                    except Exception:
                        registro.warning("não consegui avisar a espera do limite", exc_info=True)
                await self._dormir(espera)
