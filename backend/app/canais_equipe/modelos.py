"""Tipos dos canais de equipe (tabelas canais_equipe, mensagens_canal e tarefas_canal)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

MAX_MEMBROS = 12
MAX_NOME_CANAL = 60
MAX_PROPOSITO = 500
MAX_INSTRUCOES = 4_000
MAX_TEXTO_MENSAGEM = 16_000

MAX_DELEGACOES_POR_PEDIDO = 8
"""Quantas tarefas filhas um pedido do usuário pode gerar no total (todas as gerações)."""

MAX_TAREFAS_RODANDO_POR_CANAL = 2
"""O resto espera na fila do canal; não é recusado."""


class AutorCanal(StrEnum):
    USUARIO = "usuario"
    AGENTE = "agente"
    SISTEMA = "sistema"


class TipoMensagemCanal(StrEnum):
    MENSAGEM = "mensagem"
    ATIVIDADE = "atividade"
    """Linha de registro ("Sora passou para Atlas", "Heitor parou a tarefa"). Não vai para o
    pacote de contexto dos agentes e não conta como não lida."""
    RESULTADO = "resultado"


class StatusTarefa(StrEnum):
    NA_FILA = "na_fila"
    RODANDO = "rodando"
    AGUARDANDO_FILHAS = "aguardando_filhas"
    PARADA = "parada"
    CONCLUIDA = "concluida"
    FALHOU = "falhou"
    CANCELADA = "cancelada"


ABERTAS = frozenset(
    {
        StatusTarefa.NA_FILA,
        StatusTarefa.RODANDO,
        StatusTarefa.AGUARDANDO_FILHAS,
        StatusTarefa.PARADA,
    }
)
EM_ANDAMENTO = frozenset(
    {StatusTarefa.NA_FILA, StatusTarefa.RODANDO, StatusTarefa.AGUARDANDO_FILHAS}
)


class MotivoParada(StrEnum):
    PARADA_PELO_USUARIO = "parada_pelo_usuario"
    CANAL_ARQUIVADO = "canal_arquivado"
    LIDER_NECESSARIO = "lider_necessario"
    ROTEAMENTO_ILEGIVEL = "roteamento_ilegivel"
    INTERROMPIDA = "interrompida"
    """O servidor reiniciou no meio do turno; o usuário decide se repete."""
    DONO_SAIU = "dono_saiu"
    """O responsável foi tirado do canal; a tarefa espera ser reatribuída."""


class ErroCanal(Exception):
    """Pedido recusado; o texto vai para o usuário ou para o agente."""


@dataclass(slots=True)
class Canal:
    id: UUID
    usuario_id: UUID
    nome: str
    proposito: str = ""
    instrucoes: str = ""
    membros: list[UUID] = field(default_factory=list)
    lider_id: UUID | None = None
    resumo: str | None = None
    resumo_ate_seq: int | None = None
    pedidos_sem_lider: list[UUID] = field(default_factory=list)
    """Mensagens que precisavam do líder quando o canal não tinha um. Rodam ao escolher um."""
    arquivado_em: datetime | None = None
    criado_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def arquivado(self) -> bool:
        return self.arquivado_em is not None


@dataclass(frozen=True, slots=True)
class MensagemCanal:
    id: UUID
    canal_id: UUID
    seq: int
    autor: AutorCanal
    texto: str
    agente_id: UUID | None = None
    tipo: TipoMensagemCanal = TipoMensagemCanal.MENSAGEM
    responde_a: UUID | None = None
    tarefa_id: UUID | None = None
    anexos: tuple[UUID, ...] = ()
    criada_em: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class TarefaCanal:
    id: UUID
    canal_id: UUID
    pedido_id: UUID
    """Mensagem do canal que originou a tarefa (o pedido do usuário, ou a delegação)."""
    dono_id: UUID
    instrucao: str
    raiz_id: UUID
    pai_id: UUID | None = None
    delegada_por: UUID | None = None
    status: StatusTarefa = StatusTarefa.NA_FILA
    motivo: MotivoParada | None = None
    revisao: int = 1
    """Sobe a cada Retomar, Reatribuir ou transferência; resultado de revisão velha é recusado."""
    seguimentos: list[UUID] = field(default_factory=list)
    """Mensagens do usuário que chegaram depois e continuam esta tarefa."""
    resultado: str | None = None
    erro: str | None = None
    criada_em: datetime = field(default_factory=lambda: datetime.now(UTC))
    atualizada_em: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def raiz(self) -> bool:
        return self.pai_id is None
