"""Trabalho parado: lembra o usuário e depois cancela etapas que ficaram esperando demais, e
recupera etapas cujo worker morreu.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``core/src/stuck-work.ts``
(``STUCK_WORK_NOTIFY_AFTER_MS``, ``STUCK_WORK_EXPIRE_AFTER_MS``, ``stuckWorkAction``) e
``adapters/src/stuck-work.ts`` (o reconciliador que roda junto com a fila).

Regras:

- esperando o usuário (pergunta ou aprovação) ou na fila sem começar: lembra uma vez depois de
  4 h e cancela depois de 24 h, deixando uma linha de status na conversa;
- ``executando`` há mais que o prazo da etapa (5 min) com folga: o worker morreu; a etapa
  volta para a fila uma vez e, se acontecer de novo, falha.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.ferramentas.base import PRAZO_ETAPA_SEGUNDOS

AVISAR_DEPOIS = timedelta(hours=4)
CANCELAR_DEPOIS = timedelta(hours=24)
FOLGA_EXECUCAO = timedelta(minutes=2)
MAX_RETOMADAS = 1

STATUS_ESPERANDO = frozenset({"pendente", "aguardando_usuario", "aguardando_aprovacao"})


class Acao(StrEnum):
    NADA = "nada"
    AVISAR = "avisar"
    CANCELAR = "cancelar"
    RETOMAR = "retomar"
    FALHAR = "falhar"


@dataclass(frozen=True, slots=True)
class EtapaParada:
    etapa_id: str
    status: str
    desde: datetime
    """Quando entrou no status atual (``iniciada_em`` ou o último evento)."""
    ja_avisado: bool = False
    retomadas: int = 0


def acao_para(etapa: EtapaParada, agora: datetime) -> Acao:
    idade = agora - etapa.desde
    if etapa.status == "executando":
        if idade < timedelta(seconds=PRAZO_ETAPA_SEGUNDOS) + FOLGA_EXECUCAO:
            return Acao.NADA
        return Acao.RETOMAR if etapa.retomadas < MAX_RETOMADAS else Acao.FALHAR
    if etapa.status not in STATUS_ESPERANDO:
        return Acao.NADA
    if idade >= CANCELAR_DEPOIS:
        return Acao.CANCELAR
    if idade >= AVISAR_DEPOIS and not etapa.ja_avisado:
        return Acao.AVISAR
    return Acao.NADA


def mensagem_de_status(status: str) -> str:
    """Linha que fica na conversa quando a espera é cancelada."""
    return {
        "pendente": "Parei. Esta etapa ficou na fila sem começar.",
        "aguardando_usuario": "Parei. Esta etapa ainda esperava a sua resposta.",
        "aguardando_aprovacao": "Parei. Esta etapa ainda esperava a sua aprovação.",
    }.get(status, "Parei. Esta etapa ficou parada tempo demais.")


def lembrete(nome_agente: str, status: str) -> str:
    """Texto do aviso de 4 h (notificação ou ilha)."""
    if status == "aguardando_aprovacao":
        return f"{nome_agente} está esperando a sua aprovação."
    if status == "aguardando_usuario":
        return f"{nome_agente} está esperando a sua resposta."
    return f"{nome_agente} ainda não conseguiu começar."
