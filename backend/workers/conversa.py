"""Job de resposta direta (especificação §2, "O que acontece num POST
/mensagens", passos 3 e 5; §6, ``responder_direto``).

Resposta em streaming no modo ``direto`` (N1 ou N2) ou num agente individual.
"""

from __future__ import annotations

from typing import Any


async def responder_direto(ctx: dict[str, Any], mensagem_id: str) -> None:
    """Roda a Sora (ou o agente individual) e manda o texto pelos eventos
    ``mensagem.*``, terminando com ``sugestoes``. Quem põe na fila: a API."""
    raise NotImplementedError
