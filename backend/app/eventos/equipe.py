"""Eventos novos para a interface: medidor de contexto, fila, canais, reações e abas.

Ficam fora da união ``Evento`` de ``app/eventos/tipos.py`` (o contrato que o app já consome e
que ``tests/contrato`` congela). Entram nela quando o worker passar a emiti-los e o app tiver
as telas — junto com os exemplos JSON de ``tests/contrato``.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal, get_args
from uuid import UUID

from pydantic import BaseModel, Field

from app.eventos.tipos import EventoBase


class ContextoAtualizado(EventoBase):
    evento: ClassVar[Literal["contexto.atualizado"]] = "contexto.atualizado"
    agente_id: UUID
    fio: str
    porcentagem: int = Field(ge=0, le=100)
    tokens: int
    janela: int
    estimado: bool
    nivel: Literal["ok", "atencao", "compactar", "cheio"]
    compactacao: Literal["parada", "compactando", "falhou"]


class ItemFilaResumo(BaseModel):
    item_id: UUID
    seq: int
    pista: str
    origem: str
    previa: str = Field(max_length=200)
    status: str
    esperando_por: str | None = None
    em_edicao: bool = False


class FilaAtualizada(EventoBase):
    evento: ClassVar[Literal["fila.atualizada"]] = "fila.atualizada"
    agente_id: UUID
    pausada: bool
    limite_tarefas: int
    itens: list[ItemFilaResumo]


class MensagemCanalEvento(EventoBase):
    evento: ClassVar[Literal["canal.mensagem"]] = "canal.mensagem"
    canal_id: UUID
    mensagem_id: UUID
    seq: int
    autor: Literal["usuario", "agente", "sistema"]
    agente_id: UUID | None = None
    tipo: Literal["mensagem", "atividade", "resultado"]
    texto: str
    responde_a: UUID | None = None
    tarefa_id: UUID | None = None
    anexos: list[UUID] = Field(default_factory=list)
    criada_em: datetime


class TarefaCanalAtualizada(EventoBase):
    evento: ClassVar[Literal["canal.tarefa"]] = "canal.tarefa"
    canal_id: UUID
    tarefa_id: UUID
    dono_id: UUID
    pai_id: UUID | None = None
    status: Literal[
        "na_fila", "rodando", "aguardando_filhas", "parada", "concluida", "falhou", "cancelada"
    ]
    motivo: str | None = None
    revisao: int
    acoes: list[Literal["parar", "retomar", "reatribuir", "cancelar"]]
    """Botões que a interface mostra para esta tarefa agora."""


class CanalAtualizado(EventoBase):
    evento: ClassVar[Literal["canal.atualizado"]] = "canal.atualizado"
    canal_id: UUID
    nome: str
    membros: list[UUID]
    lider_id: UUID | None = None
    arquivado: bool


class ReacaoEvento(EventoBase):
    evento: ClassVar[Literal["reacao"]] = "reacao"
    mensagem_id: UUID
    emoji: str
    autor: Literal["usuario", "agente"]
    agente_id: UUID | None = None
    ligada: bool


class AbaNavegadorEvento(EventoBase):
    evento: ClassVar[Literal["navegador.aba"]] = "navegador.aba"
    aba_id: UUID
    agente_id: UUID
    url: str
    titulo: str
    carregada: bool
    assumida_pelo_usuario: bool
    fechada: bool = False
    pedido_de_ajuda: str | None = None


EventoEquipe = (
    ContextoAtualizado
    | FilaAtualizada
    | MensagemCanalEvento
    | TarefaCanalAtualizada
    | CanalAtualizado
    | ReacaoEvento
    | AbaNavegadorEvento
)

TIPOS_EVENTOS_EQUIPE = frozenset(m.evento for m in get_args(EventoEquipe))


def acoes_da_tarefa(status: str) -> list[Literal["parar", "retomar", "reatribuir", "cancelar"]]:
    """Os mesmos estados que ``app/canais_equipe/servico.py`` aceita em cada controle."""
    if status in ("na_fila", "rodando", "aguardando_filhas"):
        return ["parar"]
    if status in ("parada", "falhou"):
        return ["retomar", "reatribuir", "cancelar"]
    return []
