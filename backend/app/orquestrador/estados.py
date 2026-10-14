"""Estados da cadeia e das etapas (especificação §1, tipos ``status_cadeia`` e
``status_etapa``, e §6, diagrama "estados de uma cadeia").

A cadeia só chega a ``concluida`` passando pelo Verificador. As transições
permitidas ficam aqui, num lugar só, para os jobs e os testes unitários.
Os enums em si são os centrais de ``app.modelos.enumeracoes`` (os mesmos do SQL).
"""

from enum import StrEnum

from app.modelos.enumeracoes import StatusCadeia, StatusEtapa

__all__ = [
    "FINAIS_CADEIA",
    "FINAIS_ETAPA",
    "TRANSICOES_CADEIA",
    "TRANSICOES_ETAPA",
    "StatusAgenteApp",
    "StatusCadeia",
    "StatusEtapa",
    "TransicaoInvalida",
    "pode_mudar_cadeia",
    "pode_mudar_etapa",
    "status_do_agente",
]


class StatusAgenteApp(StrEnum):
    """Status do agente como o app mostra (§3.2), derivado de ``etapas.status``."""

    AGUARDANDO = "aguardando"
    TRABALHANDO = "trabalhando"
    CONCLUIDO = "concluido"
    ERRO = "erro"


FINAIS_CADEIA: frozenset[StatusCadeia] = frozenset(
    {StatusCadeia.CONCLUIDA, StatusCadeia.FALHOU, StatusCadeia.CANCELADA}
)
FINAIS_ETAPA: frozenset[StatusEtapa] = frozenset(
    {StatusEtapa.CONCLUIDA, StatusEtapa.REPROVADA, StatusEtapa.FALHOU, StatusEtapa.CANCELADA}
)

TRANSICOES_CADEIA: dict[StatusCadeia, frozenset[StatusCadeia]] = {}
"""De → para permitidos em ``cadeias.status``. Preenchido na etapa de lógica."""

TRANSICOES_ETAPA: dict[StatusEtapa, frozenset[StatusEtapa]] = {}
"""De → para permitidos em ``etapas.status``. Preenchido na etapa de lógica."""


class TransicaoInvalida(Exception):
    """Mudança de estado que a máquina de estados não permite."""


def pode_mudar_cadeia(de: StatusCadeia, para: StatusCadeia) -> bool:
    """Diz se a cadeia pode ir de ``de`` para ``para``."""
    raise NotImplementedError


def pode_mudar_etapa(de: StatusEtapa, para: StatusEtapa) -> bool:
    """Diz se a etapa pode ir de ``de`` para ``para``."""
    raise NotImplementedError


def status_do_agente(status_etapa: StatusEtapa) -> StatusAgenteApp:
    """Converte o status da etapa no status do agente mostrado no app (§3.2)."""
    raise NotImplementedError
