"""Resposta silenciosa das rotinas: quando não há nada a relatar, a rotina termina sem
mandar mensagem.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``adapters/src/silent-reply.ts``
(``NO_RESPONSE``, ``isExactNoResponse``, ``stripNoResponseReply``) e
``ROUTINE_SILENT_REPLY_GUIDANCE`` em ``executor.ts``.

O modelo escreve exatamente ``SEM_RESPOSTA`` como resposta final inteira. Repetido (o modelo às
vezes reescreve depois de cada lote de ferramentas: ``SEM_RESPOSTASEM_RESPOSTA``) continua
silêncio. Com qualquer outro texto em volta, a resposta fica (falha fechada) e só o marcador
solto nas pontas some.
"""

from __future__ import annotations

import re

SEM_RESPOSTA = "SEM_RESPOSTA"

_SO_MARCADOR = re.compile(rf"^(?:{SEM_RESPOSTA}\s*)+$")
_PONTA_INICIO = re.compile(rf"^\s*(?:{SEM_RESPOSTA}(?![A-Za-z0-9_])\s*)+")
_PONTA_FIM = re.compile(rf"(?:(?<![A-Za-z0-9_]){SEM_RESPOSTA}\s*)+$")

INSTRUCAO_ROTINA_SILENCIOSA = (
    "Se o pedido desta rotina disser para ficar em silêncio quando não houver nada a relatar, a "
    f"resposta final inteira deve ser exatamente {SEM_RESPOSTA}: sem texto em volta, sem "
    "variações, sem aviso de progresso, sem 'tudo certo' e sem comentar que vai ficar em "
    "silêncio. Não mande avisos se não tiver nada a relatar."
)


def e_silencio(texto: str) -> bool:
    """O texto é só o marcador (uma ou mais vezes)."""
    return bool(_SO_MARCADOR.match(texto.strip()))


def limpar_resposta(texto: str) -> str | None:
    """``None`` quando a rotina ficou em silêncio; senão o texto sem marcadores soltos nas pontas.

    Um marcador grudado numa palavra (``SEM_RESPOSTA_PADRAO``) é palavra, não marcador.
    """
    if e_silencio(texto):
        return None
    limpo = _PONTA_INICIO.sub("", texto)
    limpo = _PONTA_FIM.sub("", limpo)
    return limpo.strip()
