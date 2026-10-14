"""Modelos dos eventos públicos enviados por SSE; especificação §2."""

from datetime import datetime
from typing import Any, ClassVar, Literal, get_args
from uuid import UUID

from pydantic import BaseModel, Field

from app.modelos.enumeracoes import (
    AutorMensagem,
    Movimento,
    Nivel,
    StatusAprovacao,
    StatusCadeia,
    StatusEtapa,
    StatusPasso,
    TipoAgente,
    TipoConversa,
    TipoEntrega,
    TipoPasso,
    TipoProvedor,
)


class EventoBase(BaseModel):
    """Envelope comum serializado no campo `data` do SSE."""

    evento: ClassVar[str]


class MensagemInicio(EventoBase):
    evento: ClassVar[Literal["mensagem.inicio"]] = "mensagem.inicio"
    mensagem_id: UUID
    autor: AutorMensagem
    agente_id: UUID | None = None


class MensagemDelta(EventoBase):
    evento: ClassVar[Literal["mensagem.delta"]] = "mensagem.delta"
    mensagem_id: UUID
    texto: str


class MensagemFim(EventoBase):
    evento: ClassVar[Literal["mensagem.fim"]] = "mensagem.fim"
    mensagem_id: UUID
    anexos: list[UUID] = Field(default_factory=list)


class RoteamentoEvento(EventoBase):
    evento: ClassVar[Literal["roteamento"]] = "roteamento"
    modo: Literal["direto", "cadeia", "pergunta"]
    dificuldade: Literal[1, 2, 3]
    especialistas: list[str]
    nivel: Nivel
    provedor: TipoProvedor
    modelo: str


class ConversaAtualizada(EventoBase):
    evento: ClassVar[Literal["conversa.atualizada"]] = "conversa.atualizada"
    conversa_id: UUID
    titulo: str | None = None
    tipo: TipoConversa
    aprovada_versao: int | None = None


class AgenteCriado(EventoBase):
    evento: ClassVar[Literal["agente.criado"]] = "agente.criado"
    agente_id: UUID
    tipo: TipoAgente
    nome: str
    funcao: str
    cor: str
    movimento: Movimento


class EtapaPlano(BaseModel):
    etapa_id: UUID
    ordem: int
    especialista: str
    agente_id: UUID
    titulo: str
    nivel: Nivel
    depende_de: list[int] = Field(default_factory=list)


class CadeiaCriada(EventoBase):
    evento: ClassVar[Literal["cadeia.criada"]] = "cadeia.criada"
    cadeia_id: UUID
    versao: int
    etapas: list[EtapaPlano]


class EtapaAtualizada(EventoBase):
    evento: ClassVar[Literal["etapa.atualizada"]] = "etapa.atualizada"
    etapa_id: UUID
    status: StatusEtapa
    progresso: int = Field(ge=0, le=100)
    modelo: str | None = None
    tokens: int
    custo_usd: float


class PassoEvento(EventoBase):
    evento: ClassVar[Literal["passo"]] = "passo"
    passo_id: UUID
    etapa_id: UUID
    agente_id: UUID
    tipo: TipoPasso
    texto: str
    ferramenta: str | None = None
    acao: str | None = None
    parametros: dict[str, Any] | None = None
    resultado: dict[str, Any] | None = None
    status: StatusPasso
    para_agente_id: UUID | None = None


class EntregaEvento(EventoBase):
    evento: ClassVar[Literal["entrega"]] = "entrega"
    entrega_id: UUID
    agente_id: UUID
    versao: int
    tipo: TipoEntrega
    titulo: str
    resumo: str


class CadeiaAtualizada(EventoBase):
    evento: ClassVar[Literal["cadeia.atualizada"]] = "cadeia.atualizada"
    cadeia_id: UUID
    status: StatusCadeia
    tokens_usados: int
    custo_usd: float


class OpcaoPergunta(BaseModel):
    rotulo: str
    valor: str


class PerguntaEvento(EventoBase):
    evento: ClassVar[Literal["pergunta"]] = "pergunta"
    pergunta_id: UUID
    texto: str
    opcoes: list[OpcaoPergunta]
    resposta_livre: bool


class AprovacaoPedida(EventoBase):
    evento: ClassVar[Literal["aprovacao.pedida"]] = "aprovacao.pedida"
    aprovacao_id: UUID
    resumo: str
    dano: str
    quem_recebe: str | None
    expira_em: datetime


class AprovacaoResolvida(EventoBase):
    evento: ClassVar[Literal["aprovacao.resolvida"]] = "aprovacao.resolvida"
    aprovacao_id: UUID
    status: StatusAprovacao


class SugestoesEvento(EventoBase):
    evento: ClassVar[Literal["sugestoes"]] = "sugestoes"
    itens: list[str]


class ErroEvento(EventoBase):
    evento: ClassVar[Literal["erro"]] = "erro"
    codigo: str
    mensagem: str


class PingEvento(EventoBase):
    evento: ClassVar[Literal["ping"]] = "ping"


Evento = (
    MensagemInicio
    | MensagemDelta
    | MensagemFim
    | RoteamentoEvento
    | ConversaAtualizada
    | AgenteCriado
    | CadeiaCriada
    | EtapaAtualizada
    | PassoEvento
    | EntregaEvento
    | CadeiaAtualizada
    | PerguntaEvento
    | AprovacaoPedida
    | AprovacaoResolvida
    | SugestoesEvento
    | ErroEvento
    | PingEvento
)

EventoEstado = (
    ConversaAtualizada
    | AgenteCriado
    | CadeiaCriada
    | EtapaAtualizada
    | PassoEvento
    | EntregaEvento
    | CadeiaAtualizada
    | AprovacaoPedida
    | AprovacaoResolvida
)

TIPOS_EVENTOS_ESTADO = frozenset(modelo.evento for modelo in get_args(EventoEstado))
"""Lista central dos eventos que também vão ao stream agregado do usuário."""


class EnvelopeEventoUsuario(BaseModel):
    """Evento de estado enriquecido para o canal agregado do usuário."""

    conversa_id: UUID
    evento: EventoEstado
