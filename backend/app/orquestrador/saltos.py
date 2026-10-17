"""Limite de saltos nas mensagens entre agentes.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``core/src/bot-messages.ts``
(``DEFAULT_BOT_MESSAGE_MAX_HOPS``, ``nextBotMessageHop``, ``botMessageHopExhausted``).

Mensagem entre agentes é "dispara e esquece": nada impede dois agentes de responderem um
ao outro para sempre e queimarem a API do usuário. Cada mensagem enviada **por um agente**
carrega um contador de saltos; a mensagem do usuário sempre começa uma corrente nova no
salto 0. Passou do limite, a entrega é recusada e o agente recebe um erro de ferramenta.

Vale para ``enviar_para_agente`` (fase 2), ``mensagem_especialista`` e qualquer handoff
entre especialistas da cadeia.
"""

from __future__ import annotations

import os

from app.ferramentas.base import ErroFerramenta

MAX_SALTOS_PADRAO = 6
"""Quantas entregas iniciadas por agentes podem se encadear antes da próxima ser recusada."""

MAX_CARACTERES_MENSAGEM = 8_000
"""Tamanho máximo de uma mensagem entre agentes."""


def max_saltos() -> int:
    """``SORA_MAX_SALTOS`` quando é inteiro positivo; senão o padrão (6)."""
    bruto = os.environ.get("SORA_MAX_SALTOS", "").strip()
    try:
        valor = int(bruto) if bruto else MAX_SALTOS_PADRAO
    except ValueError:
        return MAX_SALTOS_PADRAO
    return valor if valor >= 1 else MAX_SALTOS_PADRAO


def proximo_salto(salto_de_origem: int | None) -> int:
    """Salto da mensagem que um agente vai mandar agora.

    ``None`` ou 0 = a origem foi o usuário (corrente nova) → 1.
    """
    if isinstance(salto_de_origem, int) and not isinstance(salto_de_origem, bool):
        if salto_de_origem > 0:
            return salto_de_origem + 1
    return 1


def saltos_esgotados(salto: int) -> bool:
    return salto > max_saltos()


class SaltosEsgotados(ErroFerramenta):
    """A corrente de mensagens entre agentes passou do limite."""


def conferir_envio(salto_de_origem: int | None) -> int:
    """Calcula o salto da nova mensagem ou recusa a entrega.

    O texto do erro volta para o modelo: ele deve seguir sozinho e responder ao usuário,
    não tentar de novo.
    """
    salto = proximo_salto(salto_de_origem)
    if saltos_esgotados(salto):
        raise SaltosEsgotados(
            f"Mensagem não enviada: a conversa entre agentes passou de {max_saltos()} trocas "
            "seguidas sem o usuário. Termine o trabalho com o que já tem e responda ao usuário."
        )
    return salto
