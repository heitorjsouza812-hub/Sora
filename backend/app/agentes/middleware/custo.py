"""Grava em ``chamadas_modelo`` o custo de cada chamada do agente (Sora, bots, grupo, cadeia).

Sem isto o "Uso do mês" e o teto de gasto por provedor só contavam a triagem e as imagens. O
seletor deixa em ``model.metadata["sora_custo"]`` o provedor, o nível, o papel e o preço do
modelo (``app/orquestrador/modelos.py``); aqui a resposta do provedor vira uma linha. Fica por
dentro da troca de modelo: se o principal falhou e um reserva respondeu, a linha é do reserva.

Gravar nunca derruba o turno: falha no banco vai para o log.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from app.llm.custo import CustoChamada, PrecoModelo, UsoTokens, calcular_custo, extrair_uso

registro = logging.getLogger(__name__)

CHAVE_DE_CUSTO = "sora_custo"

Gravar = Callable[[CustoChamada], Awaitable[None]]


def marcar_custo(
    chat: Any,
    *,
    modelo: str,
    provedor_id: UUID,
    nivel: str,
    papel: str,
    preco_entrada: Decimal | None,
    preco_saida: Decimal | None,
) -> None:
    """Deixa no modelo o que o middleware precisa para gravar a linha de custo."""
    chat.metadata = {
        **(chat.metadata or {}),
        CHAVE_DE_CUSTO: {
            "modelo": modelo,
            "provedor_id": str(provedor_id),
            "nivel": nivel,
            "papel": papel,
            "preco_entrada": None if preco_entrada is None else str(preco_entrada),
            "preco_saida": None if preco_saida is None else str(preco_saida),
        },
    }


def _preco(dados: dict[str, Any]) -> PrecoModelo:
    def decimal(valor: Any) -> Decimal | None:
        return None if valor is None else Decimal(str(valor))

    return PrecoModelo(
        entrada=decimal(dados.get("preco_entrada")), saida=decimal(dados.get("preco_saida"))
    )


def custo_da_resposta(modelo: Any, resposta: Any, latencia_ms: int) -> CustoChamada | None:
    """Linha de custo da chamada, ou ``None`` se o modelo não é do seletor (modelo falso) ou o
    provedor não informou o uso."""
    dados = (getattr(modelo, "metadata", None) or {}).get(CHAVE_DE_CUSTO)
    if not isinstance(dados, dict):
        return None
    mensagens = getattr(resposta, "result", None)
    if mensagens is None:
        mensagens = [resposta]
    entrada = saida = 0
    for mensagem in mensagens:
        uso = extrair_uso(mensagem)
        entrada += uso.tokens_entrada
        saida += uso.tokens_saida
    if entrada == 0 and saida == 0:
        return None
    uso_total = UsoTokens(tokens_entrada=entrada, tokens_saida=saida)
    return CustoChamada(
        modelo=str(dados["modelo"]),
        provedor_id=UUID(str(dados["provedor_id"])),
        papel=str(dados["papel"]),
        nivel=str(dados["nivel"]),
        tokens_entrada=entrada,
        tokens_saida=saida,
        custo_usd=calcular_custo(str(dados["modelo"]), uso_total, _preco(dados)),
        latencia_ms=latencia_ms,
    )


class MiddlewareCustoDasChamadas(AgentMiddleware):
    def __init__(self, gravar: Gravar) -> None:
        self._gravar = gravar

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> Any:
        inicio = time.perf_counter()
        resposta = await handler(request)
        try:
            custo = custo_da_resposta(
                request.model, resposta, int((time.perf_counter() - inicio) * 1000)
            )
            if custo is not None:
                await self._gravar(custo)
        except Exception:
            registro.warning("não consegui gravar o custo da chamada ao modelo", exc_info=True)
        return resposta
