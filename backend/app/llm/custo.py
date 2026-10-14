"""Custo e uso de tokens de cada chamada de modelo.

Especificação: §1 (tabela ``chamadas_modelo``), §5 (o usuário paga cada provedor direto e a Sora
mostra quanto gastou) e §6 "Orçamento" (o valor real corrige a reserva feita no Redis).

O custo vem do preço do catálogo (``PrecoModelo``) quando existe; senão, do mapa de custos do
LiteLLM (``litellm.model_cost``). Modelo sem preço em nenhum dos dois custa 0 (não inventamos).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel

if TYPE_CHECKING:
    from langchain_core.messages import AIMessage
    from sqlalchemy.ext.asyncio import AsyncSession

UM_MILHAO = Decimal(1_000_000)
_SEIS_CASAS = Decimal("0.000001")


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


def _inteiro(valor: Any) -> int:
    try:
        return max(int(valor), 0)
    except (TypeError, ValueError):
        return 0


def extrair_uso(resposta: AIMessage) -> UsoTokens:
    """Lê os tokens da resposta do LangChain (``usage_metadata``, ou o uso cru do provedor)."""
    metadados = getattr(resposta, "usage_metadata", None)
    if metadados:
        return UsoTokens(
            tokens_entrada=_inteiro(metadados.get("input_tokens")),
            tokens_saida=_inteiro(metadados.get("output_tokens")),
        )
    cru = getattr(resposta, "response_metadata", None) or {}
    uso = cru.get("token_usage") or cru.get("usage") or {}
    entrada = uso.get("prompt_tokens", uso.get("input_tokens"))
    saida = uso.get("completion_tokens", uso.get("output_tokens"))
    return UsoTokens(tokens_entrada=_inteiro(entrada), tokens_saida=_inteiro(saida))


def _info_litellm(modelo: str) -> dict[str, Any] | None:
    """Linha do ``litellm.model_cost`` para o modelo (tenta o nome e variações sem prefixo)."""
    import litellm

    mapa = litellm.model_cost
    candidatos = [modelo]
    if modelo.startswith("openrouter/"):
        candidatos.append(modelo.removeprefix("openrouter/"))
    if "/" in modelo:
        candidatos.append(modelo.split("/", 1)[1])
    for nome in candidatos:
        info = mapa.get(nome)
        if isinstance(info, dict):
            return info
    return None


def precos_litellm(modelo: str) -> PrecoModelo | None:
    """Preço do modelo no mapa do LiteLLM, em US$ por 1M de tokens (``None`` se não houver)."""
    info = _info_litellm(modelo)
    if info is None:
        return None
    entrada = info.get("input_cost_per_token")
    saida = info.get("output_cost_per_token")
    if entrada is None and saida is None:
        return None
    return PrecoModelo(
        entrada=None if entrada is None else Decimal(str(entrada)) * UM_MILHAO,
        saida=None if saida is None else Decimal(str(saida)) * UM_MILHAO,
    )


def contexto_litellm(modelo: str) -> int | None:
    """Janela de contexto do modelo no mapa do LiteLLM (``None`` se não houver)."""
    info = _info_litellm(modelo)
    if info is None:
        return None
    valor = info.get("max_input_tokens") or info.get("max_tokens")
    return int(valor) if valor else None


def calcular_custo(modelo: str, uso: UsoTokens, preco: PrecoModelo | None = None) -> Decimal:
    """Custo em US$ da chamada: preço do catálogo se houver, senão o mapa do LiteLLM."""
    if preco is None or (preco.entrada is None and preco.saida is None):
        preco = precos_litellm(modelo)
    if preco is None:
        return Decimal(0)
    entrada = (preco.entrada or Decimal(0)) * uso.tokens_entrada / UM_MILHAO
    saida = (preco.saida or Decimal(0)) * uso.tokens_saida / UM_MILHAO
    return (entrada + saida).quantize(_SEIS_CASAS)


def inicio_do_mes(agora: datetime | None = None) -> datetime:
    """Primeiro instante do mês corrente em UTC (janela do teto mensal por provedor)."""
    agora = agora or datetime.now(UTC)
    return agora.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def gravar_chamada(
    sessao: AsyncSession,
    usuario_id: UUID,
    custo: CustoChamada,
    *,
    cadeia_id: UUID | None = None,
    etapa_id: UUID | None = None,
) -> None:
    """Grava a chamada em ``chamadas_modelo`` (``flush``; o commit é de quem abriu a sessão)."""
    from app.modelos.tabelas import ChamadaModelo

    sessao.add(
        ChamadaModelo(
            usuario_id=usuario_id,
            cadeia_id=cadeia_id,
            etapa_id=etapa_id,
            provedor_id=custo.provedor_id,
            papel=custo.papel,
            modelo=custo.modelo,
            nivel=custo.nivel,
            tokens_entrada=custo.tokens_entrada,
            tokens_saida=custo.tokens_saida,
            custo_usd=custo.custo_usd,
            latencia_ms=custo.latencia_ms,
        )
    )
    await sessao.flush()


async def gasto_do_mes_por_provedor(
    sessao: AsyncSession, usuario_id: UUID, *, agora: datetime | None = None
) -> dict[UUID, Decimal]:
    """Gasto do mês corrente por ``provedor_id``: alimenta o teto do seletor e ``GET /v1/uso``."""
    from sqlalchemy import func, select

    from app.modelos.tabelas import ChamadaModelo

    consulta = (
        select(ChamadaModelo.provedor_id, func.coalesce(func.sum(ChamadaModelo.custo_usd), 0))
        .where(
            ChamadaModelo.usuario_id == usuario_id,
            ChamadaModelo.provedor_id.is_not(None),
            ChamadaModelo.criado_em >= inicio_do_mes(agora),
        )
        .group_by(ChamadaModelo.provedor_id)
    )
    linhas = (await sessao.execute(consulta)).all()
    return {provedor_id: Decimal(total) for provedor_id, total in linhas}
