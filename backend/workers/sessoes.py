"""Rotina de higiene das sessões de login (Cerca M4, etapa 5)."""

from __future__ import annotations

import logging
from typing import Any

registro = logging.getLogger(__name__)


async def limpar_pares_de_renovacao(ctx: dict[str, Any]) -> int:
    """Zera o par de tokens cifrado das sessões cuja janela de recuperação (30 s) já fechou."""
    from app.core import contas

    try:
        async with ctx["sessoes"]() as sessao:
            limpas = await contas.limpar_pares_vencidos(sessao)
    except Exception:
        registro.warning("não consegui limpar os pares de renovação vencidos", exc_info=True)
        return 0
    if limpas:
        registro.info("%d par(es) de renovação vencidos apagados", limpas)
    return limpas


async def apagar_sessoes_vencidas(ctx: dict[str, Any]) -> int:
    """Apaga as sessões vencidas ou encerradas há mais de 30 dias (a tabela não cresce sem fim)."""
    from app.core import contas

    try:
        async with ctx["sessoes"]() as sessao:
            apagadas = await contas.apagar_sessoes_vencidas(sessao)
            tokens = await contas.apagar_tokens_email_vencidos(sessao)
    except Exception:
        registro.warning("não consegui apagar as sessões vencidas", exc_info=True)
        return 0
    if apagadas:
        registro.info("%d sessão(ões) vencida(s) apagada(s)", apagadas)
    if tokens:
        registro.info("%d link(s) de e-mail vencido(s) apagado(s)", tokens)
    return apagadas
