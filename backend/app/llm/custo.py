"""Custo e uso de tokens de cada chamada de modelo.

Especificação: §1 (tabela ``chamadas_modelo``), §5 (o usuário paga cada provedor direto e a Sora
mostra quanto gastou) e §6 "Orçamento" (o valor real corrige a reserva feita no Redis).

O custo vem do LiteLLM (``litellm.completion_cost`` / ``litellm.model_cost``); quando o modelo
tem preço no catálogo (``PrecoModelo``), o preço do catálogo vale.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel

if TYPE_CHECKING:
    from langchain_core.messages import AIMessage
    from sqlalchemy.ext.asyncio import AsyncSession


class PrecoModelo(BaseModel):
    """Preço em US$ por 1 milhão de tokens. ``None`` = desconhecido."""

    entrada: Decimal | None = None
    saida: Decimal | None = None


class UsoTokens(BaseModel):
    tokens_entrada: int
    tokens_saida: int


class CustoChamada(BaseModel):
    """Uma linha de ``chamadas_modelo`` (sem ids de cadeia/etapa, que são do orquestrador)."""

    modelo: str
    provedor_id: UUID | None = None
    papel: str
    nivel: str
    tokens_entrada: int
    tokens_saida: int
    custo_usd: Decimal
    latencia_ms: int


def extrair_uso(resposta: AIMessage) -> UsoTokens:
    """Lê os tokens da resposta do LangChain (``usage_metadata``)."""
    raise NotImplementedError


def calcular_custo(modelo: str, uso: UsoTokens, preco: PrecoModelo | None = None) -> Decimal:
    """Custo em US$ da chamada: preço do catálogo se houver, senão o mapa do LiteLLM."""
    raise NotImplementedError


async def gravar_chamada(sessao: AsyncSession, usuario_id: UUID, custo: CustoChamada) -> None:
    """Grava a chamada em ``chamadas_modelo``. Chamado pelo worker depois de cada modelo."""
    raise NotImplementedError


async def gasto_do_mes_por_provedor(sessao: AsyncSession, usuario_id: UUID) -> dict[UUID, Decimal]:
    """Gasto do mês corrente por ``provedor_id``: alimenta o teto do seletor e ``GET /v1/uso``."""
    raise NotImplementedError
