"""Pedido de interrupção de um turno de canal em andamento (Parar, Cancelar, Arquivar).

O turno roda num worker; quem pede é a API (ou outro worker). O recado vai por uma chave no
Redis que o worker dono do turno consulta enquanto roda. A chave expira sozinha e é apagada
quando um novo turno da tarefa começa (Retomar não pode nascer já interrompido).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

TTL_S = 300


def _chave(tarefa_id: UUID) -> str:
    return f"interromper_tarefa:{tarefa_id}"


async def pedir_interrupcao(redis: Any, tarefas: Iterable[UUID]) -> None:
    for tarefa_id in tarefas:
        await redis.set(_chave(tarefa_id), "1", ex=TTL_S)


async def interrupcao_pedida(redis: Any, tarefa_id: UUID) -> bool:
    return bool(await redis.exists(_chave(tarefa_id)))


async def limpar_interrupcao(redis: Any, tarefa_id: UUID) -> None:
    await redis.delete(_chave(tarefa_id))
