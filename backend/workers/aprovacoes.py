"""Job de prazo das aprovações (especificação §6, ``expirar_aprovacao`` e
"Aprovação no meio da etapa": prazo de 10 minutos).
"""

from __future__ import annotations

from typing import Any

PRAZO_APROVACAO_MINUTOS = 10


async def expirar_aprovacao(ctx: dict[str, Any], aprovacao_id: str) -> None:
    """Marca a aprovação como ``expirada`` (se ainda pendente), emite
    ``aprovacao.resolvida`` e retoma a etapa com "negado". Agendado para
    ``expira_em``."""
    raise NotImplementedError
