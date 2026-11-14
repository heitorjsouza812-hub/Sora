"""Arquivos que o agente produziu e ainda não foram mostrados ao usuário.

``gerar_imagem`` e ``escrever_arquivo`` criam anexos; quem os leva ao usuário é a próxima mensagem
do mesmo agente (``falar`` no chat 1:1, ``canal_resultado`` no grupo). Antes, o modelo precisava
copiar o ``anexo_id`` do retorno da ferramenta para a mensagem, e quando esquecia a imagem ficava
guardada e invisível. Agora a ferramenta registra o anexo aqui e a mensagem seguinte o recolhe.

É memória do processo do worker: um turno roda inteiro no mesmo processo, então basta. O que não for
recolhido em ``VALIDADE_S`` (1 h) é esquecido (o arquivo continua guardado e acessível por id).
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from uuid import UUID

VALIDADE_S = 3600.0
MAX_POR_AGENTE = 10

_pendentes: dict[tuple[UUID, UUID], dict[UUID, float]] = {}


def _podar(agora: float) -> None:
    for chave in list(_pendentes):
        vivos = {a: t for a, t in _pendentes[chave].items() if agora - t < VALIDADE_S}
        if vivos:
            _pendentes[chave] = vivos
        else:
            del _pendentes[chave]


def registrar(usuario_id: UUID, agente_id: UUID, anexo_id: UUID) -> None:
    """Marca ``anexo_id`` como produzido pelo agente e ainda não entregue."""
    agora = time.monotonic()
    _podar(agora)
    lista = _pendentes.setdefault((usuario_id, agente_id), {})
    lista[anexo_id] = agora
    while len(lista) > MAX_POR_AGENTE:
        lista.pop(next(iter(lista)))


def recolher(
    usuario_id: UUID, agente_id: UUID, explicitos: Iterable[UUID] = (), *, limite: int = 10
) -> list[UUID]:
    """Anexos da mensagem: os que o modelo indicou mais os pendentes, sem repetir, até ``limite``.
    Os pendentes saem do registro (cada arquivo é entregue uma vez)."""
    _podar(time.monotonic())
    pendentes = _pendentes.pop((usuario_id, agente_id), {})
    return list(dict.fromkeys([*explicitos, *pendentes]))[:limite]


def limpar() -> None:
    """Esvazia o registro (testes)."""
    _pendentes.clear()
