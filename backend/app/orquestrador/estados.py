"""Estados da cadeia e das etapas (especificação §1, tipos ``status_cadeia`` e
``status_etapa``, e §6, diagrama "estados de uma cadeia").

A cadeia só chega a ``concluida`` passando pelo Verificador. As transições
permitidas ficam aqui, num lugar só, para os jobs e os testes unitários.
Os enums em si são os centrais de ``app.modelos.enumeracoes`` (os mesmos do SQL).
"""

from enum import StrEnum

from app.modelos.enumeracoes import StatusCadeia, StatusEtapa

__all__ = [
    "EM_ANDAMENTO_ETAPA",
    "FINAIS_CADEIA",
    "FINAIS_ETAPA",
    "TRANSICOES_CADEIA",
    "TRANSICOES_ETAPA",
    "StatusAgenteApp",
    "StatusCadeia",
    "StatusEtapa",
    "TransicaoInvalida",
    "mudar_cadeia",
    "mudar_etapa",
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


_C = StatusCadeia
_E = StatusEtapa

FINAIS_CADEIA: frozenset[StatusCadeia] = frozenset({_C.CONCLUIDA, _C.FALHOU, _C.CANCELADA})
"""Estados de onde a cadeia não sai mais (um ajuste cria outra cadeia, ``versao + 1``)."""

FINAIS_ETAPA: frozenset[StatusEtapa] = frozenset(
    {_E.CONCLUIDA, _E.REPROVADA, _E.FALHOU, _E.CANCELADA}
)
"""A etapa não roda mais. ``concluida`` ainda pode virar ``reprovada`` pelo
Verificador; a nova tentativa é outra linha (``tentativa + 1``)."""

EM_ANDAMENTO_ETAPA: frozenset[StatusEtapa] = frozenset(
    {_E.EXECUTANDO, _E.AGUARDANDO_USUARIO, _E.AGUARDANDO_APROVACAO}
)
"""Ocupa uma das vagas de paralelo da cadeia."""

TRANSICOES_CADEIA: dict[StatusCadeia, frozenset[StatusCadeia]] = {
    # planejador pronto → executa; faltou dado → pergunta; erro → falha
    _C.PLANEJANDO: frozenset({_C.EXECUTANDO, _C.AGUARDANDO_USUARIO, _C.FALHOU, _C.CANCELADA}),
    # todas as etapas terminaram → verifica; orçamento estourou → pergunta
    _C.EXECUTANDO: frozenset({_C.VERIFICANDO, _C.AGUARDANDO_USUARIO, _C.FALHOU, _C.CANCELADA}),
    # aprovou → concluída; reprovou → refaz etapas; limite de rodadas → pergunta
    _C.VERIFICANDO: frozenset(
        {_C.CONCLUIDA, _C.EXECUTANDO, _C.AGUARDANDO_USUARIO, _C.FALHOU, _C.CANCELADA}
    ),
    # o usuário respondeu: volta de onde parou (nunca direto para concluída)
    _C.AGUARDANDO_USUARIO: frozenset(
        {_C.PLANEJANDO, _C.EXECUTANDO, _C.VERIFICANDO, _C.FALHOU, _C.CANCELADA}
    ),
    _C.CONCLUIDA: frozenset(),
    _C.FALHOU: frozenset(),
    _C.CANCELADA: frozenset(),
}
"""De → para permitidos em ``cadeias.status``."""

TRANSICOES_ETAPA: dict[StatusEtapa, frozenset[StatusEtapa]] = {
    _E.PENDENTE: frozenset({_E.EXECUTANDO, _E.CANCELADA}),
    # ``pendente`` de novo: o worker caiu e a etapa volta para a fila (retomada pelo checkpoint)
    _E.EXECUTANDO: frozenset(
        {
            _E.PENDENTE,
            _E.AGUARDANDO_USUARIO,
            _E.AGUARDANDO_APROVACAO,
            _E.CONCLUIDA,
            _E.FALHOU,
            _E.CANCELADA,
        }
    ),
    _E.AGUARDANDO_USUARIO: frozenset({_E.EXECUTANDO, _E.FALHOU, _E.CANCELADA}),
    _E.AGUARDANDO_APROVACAO: frozenset({_E.EXECUTANDO, _E.FALHOU, _E.CANCELADA}),
    _E.CONCLUIDA: frozenset({_E.REPROVADA}),
    _E.REPROVADA: frozenset(),
    _E.FALHOU: frozenset(),
    _E.CANCELADA: frozenset(),
}
"""De → para permitidos em ``etapas.status``."""


class TransicaoInvalida(Exception):
    """Mudança de estado que a máquina de estados não permite."""


def pode_mudar_cadeia(de: StatusCadeia, para: StatusCadeia) -> bool:
    """Diz se a cadeia pode ir de ``de`` para ``para``."""
    return para in TRANSICOES_CADEIA[StatusCadeia(de)]


def pode_mudar_etapa(de: StatusEtapa, para: StatusEtapa) -> bool:
    """Diz se a etapa pode ir de ``de`` para ``para``."""
    return para in TRANSICOES_ETAPA[StatusEtapa(de)]


def mudar_cadeia(de: StatusCadeia, para: StatusCadeia) -> StatusCadeia:
    """Devolve ``para`` se a transição vale; senão levanta ``TransicaoInvalida``."""
    if not pode_mudar_cadeia(de, para):
        raise TransicaoInvalida(f"cadeia: {de} → {para} não é permitido")
    return StatusCadeia(para)


def mudar_etapa(de: StatusEtapa, para: StatusEtapa) -> StatusEtapa:
    """Devolve ``para`` se a transição vale; senão levanta ``TransicaoInvalida``."""
    if not pode_mudar_etapa(de, para):
        raise TransicaoInvalida(f"etapa: {de} → {para} não é permitido")
    return StatusEtapa(para)


_AGENTE_POR_ETAPA: dict[StatusEtapa, StatusAgenteApp] = {
    _E.PENDENTE: StatusAgenteApp.AGUARDANDO,
    _E.EXECUTANDO: StatusAgenteApp.TRABALHANDO,
    _E.AGUARDANDO_USUARIO: StatusAgenteApp.TRABALHANDO,
    _E.AGUARDANDO_APROVACAO: StatusAgenteApp.TRABALHANDO,
    _E.CONCLUIDA: StatusAgenteApp.CONCLUIDO,
    _E.REPROVADA: StatusAgenteApp.AGUARDANDO,  # a nova tentativa vem como outra etapa
    _E.FALHOU: StatusAgenteApp.ERRO,
    _E.CANCELADA: StatusAgenteApp.AGUARDANDO,
}


def status_do_agente(status_etapa: StatusEtapa) -> StatusAgenteApp:
    """Converte o status da etapa no status do agente mostrado no app (§3.2).

    As pausas (pergunta, aprovação) contam como "trabalhando": o agente está no
    meio da tarefa. Cancelada volta a "aguardando", não é erro do agente.
    """
    return _AGENTE_POR_ETAPA[StatusEtapa(status_etapa)]
