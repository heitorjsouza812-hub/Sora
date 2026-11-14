"""Eventos novos para a interface: medidor de contexto, fila, canais, reações e abas.

Ficam fora da união ``Evento`` de ``app/eventos/tipos.py`` (o contrato que o app já consome e
que ``tests/contrato`` congela). Entram nela quando o worker passar a emiti-los e o app tiver
as telas — junto com os exemplos JSON de ``tests/contrato``.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import ClassVar, Literal, get_args
from uuid import UUID

from pydantic import BaseModel, Field

from app.atencao import PedidoAtencao
from app.eventos.tipos import EventoBase
from app.modelos.esquemas import AgenteSaida
from app.rascunhos_bot import RascunhoBotSaida, RotinaRascunhoBot

RETENCAO_EQUIPE_SEGUNDOS = 24 * 60 * 60
MAX_TEXTO_MEMORIA_EVENTO = 160


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
    proposito: str = ""
    instrucoes: str = ""
    estado: Literal["livre", "trabalhando", "precisa_de_voce"] = "livre"


class PrecisaDeVoceAtualizado(EventoBase):
    evento: ClassVar[Literal["precisa_de_voce.atualizado"]] = "precisa_de_voce.atualizado"
    agente_id: UUID | None = None
    grupo_id: UUID | None = None
    estado: Literal["livre", "trabalhando", "precisa_de_voce"]
    pedidos: list[PedidoAtencao] = Field(default_factory=list)


class BotRascunhoEvento(EventoBase):
    evento: ClassVar[Literal["bot.rascunho"]] = "bot.rascunho"
    id: UUID
    nome: str
    funcao: str
    cor: str
    instrucoes: str
    ferramentas: list[str]
    rotina: RotinaRascunhoBot | None
    status: Literal["rascunho"] = "rascunho"

    @classmethod
    def de(cls, rascunho: RascunhoBotSaida) -> BotRascunhoEvento:
        return cls(**rascunho.model_dump())


class BotRascunhoResolvido(EventoBase):
    evento: ClassVar[Literal["bot.rascunho.resolvido"]] = "bot.rascunho.resolvido"
    rascunho_id: UUID
    status: Literal["confirmado", "descartado"]
    agente_id: UUID | None = None


class GrupoPropostoEvento(EventoBase):
    evento: ClassVar[Literal["grupo.proposto"]] = "grupo.proposto"
    id: UUID
    nome: str
    pedido: str
    bots_reaproveitados: list[AgenteSaida]
    bots_novos: list[RascunhoBotSaida]
    status: Literal["proposta"] = "proposta"


class GrupoPropostaResolvida(EventoBase):
    evento: ClassVar[Literal["grupo.proposta.resolvida"]] = "grupo.proposta.resolvida"
    proposta_id: UUID
    status: Literal["aceita", "recusada"]
    grupo_id: UUID | None = None


class ReacaoEvento(EventoBase):
    evento: ClassVar[Literal["reacao"]] = "reacao"
    mensagem_id: UUID
    emoji: str
    autor: Literal["usuario", "agente"]
    agente_id: UUID | None = None
    ligada: bool


class MemoriaCriadaEvento(EventoBase):
    """O bot guardou algo na memória: o app mostra "Guardei isto" com Desfazer
    (``DELETE /v1/memorias/{memoria_id}``)."""

    evento: ClassVar[Literal["memoria.criada"]] = "memoria.criada"
    memoria_id: UUID
    agente_id: UUID | None = None
    conversa_id: UUID | None = None
    texto: str = Field(max_length=MAX_TEXTO_MEMORIA_EVENTO)
    """Começo do que foi guardado (a memória inteira vem de ``GET /v1/memorias``)."""


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
    | PrecisaDeVoceAtualizado
    | BotRascunhoEvento
    | BotRascunhoResolvido
    | GrupoPropostoEvento
    | GrupoPropostaResolvida
    | ReacaoEvento
    | MemoriaCriadaEvento
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


async def publicar_evento_equipe(redis, evento: EventoEquipe, usuario_id: UUID) -> str:
    """Publica uma peca da equipe no stream agregado consumido por ``GET /v1/eventos``."""
    from app.eventos.streams import canal_usuario, id_minimo_retido

    canal = canal_usuario(usuario_id)
    dados = json.dumps(evento.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    id_evento = await redis.xadd(
        canal,
        {"event": evento.evento, "data": dados},
        minid=id_minimo_retido(),
        approximate=False,
    )
    await redis.expire(canal, RETENCAO_EQUIPE_SEGUNDOS)
    return id_evento.decode() if isinstance(id_evento, bytes) else id_evento
