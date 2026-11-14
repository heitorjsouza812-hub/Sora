"""Turno de grupo pausado num cartão "Precisa de você".

Quando o turno de uma tarefa de grupo abre um cartão (aprovação do revisor), o worker guarda
aqui qual tarefa, revisão e thread esperam a decisão. A rota que decide o cartão enfileira
``retomar_tarefa_canal``; o worker lê esta pausa e retoma o mesmo turno do LangGraph.

Fica no Redis (o mesmo dos eventos), sem expirar sozinho: o cartão pode esperar horas. A chave
some quando a decisão é consumida.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PausaTarefa:
    tarefa_id: UUID
    revisao: int
    thread: str


def _chave(cartao_id: UUID | str) -> str:
    return f"pausa_tarefa_canal:{cartao_id}"


async def gravar_pausa(redis: Any, cartao_id: UUID | str, pausa: PausaTarefa) -> None:
    await redis.set(
        _chave(cartao_id),
        json.dumps(
            {"tarefa_id": str(pausa.tarefa_id), "revisao": pausa.revisao, "thread": pausa.thread}
        ),
    )


async def ler_pausa(redis: Any, cartao_id: UUID | str) -> PausaTarefa | None:
    bruto = await redis.get(_chave(cartao_id))
    if not bruto:
        return None
    dados = json.loads(bruto)
    return PausaTarefa(UUID(dados["tarefa_id"]), int(dados["revisao"]), str(dados["thread"]))


async def apagar_pausa(redis: Any, cartao_id: UUID | str) -> None:
    await redis.delete(_chave(cartao_id))


def cartao_da_interrupcao(resultado: dict[str, Any]) -> str | None:
    """Id do cartão (aprovação ou pergunta) que pausou o turno, ou ``None`` se não pausou."""
    interrupcoes = resultado.get("__interrupt__")
    if not interrupcoes:
        return None
    valor = getattr(interrupcoes[0], "value", interrupcoes[0])
    if not isinstance(valor, dict):
        return None
    cartao = valor.get("aprovacao_id") or valor.get("pergunta_id")
    return str(cartao) if cartao else None
