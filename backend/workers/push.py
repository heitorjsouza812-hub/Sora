"""Job da notificação no celular (``app/push.py``)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

registro = logging.getLogger(__name__)


async def enviar_push_do_pedido(
    ctx: dict[str, Any],
    usuario_id: str,
    pedido_id: str,
    tipo: str,
    agente_id: str | None = None,
    grupo_id: str | None = None,
) -> int:
    """Avisa os aparelhos da conta que há um pedido novo em "Precisa de você". Nunca levanta:
    notificação é um extra (o cartão continua no app)."""
    from app.push import carga_do_pedido, enviar_para_usuario

    try:
        async with ctx["sessoes"]() as sessao:
            carga = await carga_do_pedido(
                sessao,
                pedido_id,
                tipo,
                UUID(agente_id) if agente_id else None,
                UUID(grupo_id) if grupo_id else None,
            )
            envio = await enviar_para_usuario(sessao, UUID(usuario_id), carga)
            await sessao.commit()
    except Exception:
        registro.warning("não consegui enviar a notificação do pedido", exc_info=True)
        return 0
    return envio.enviadas
