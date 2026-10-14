"""Pedir ajuste (especificação §2, ``POST /v1/conversas/{id}/ajuste``; §6, job
``ajustar``).

Cria uma cadeia nova com ``versao + 1`` só com a etapa do especialista certo
(o escolhido pelo usuário ou o que o planejador apontar) e o Verificador.
"""

from __future__ import annotations

from uuid import UUID


async def criar_cadeia_de_ajuste(
    conversa_id: UUID, texto: str, agente_id: UUID | None = None
) -> UUID:
    """Cria a cadeia de ajuste e devolve o id dela."""
    raise NotImplementedError


async def escolher_especialista(conversa_id: UUID, texto: str) -> UUID:
    """Quando o usuário não escolheu, decide qual especialista refaz a entrega."""
    raise NotImplementedError
