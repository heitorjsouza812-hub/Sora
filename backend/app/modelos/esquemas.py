"""Esquemas Pydantic dos contratos HTTP; especificação §§2, 5 e 8.2."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modelos.enumeracoes import (
    AutorMensagem,
    DecisaoAprovacao,
    Movimento,
    Prioridade,
    StatusCadeia,
    TipoAgente,
    TipoConversa,
    TipoEntrega,
    TipoProvedor,
)


class EsquemaBase(BaseModel):
    """Base compatível com objetos ORM e nomes da API em PT-BR."""

    model_config = ConfigDict(from_attributes=True)


class CadastroEntrada(EsquemaBase):
    nome: str
    email: str
    senha: str = Field(min_length=10)
    convite: str | None = None


class LoginEntrada(EsquemaBase):
    email: str
    senha: str


class RenovacaoEntrada(EsquemaBase):
    token_renovacao: str | None = None


class TokensSaida(EsquemaBase):
    token_acesso: str
    token_renovacao: str | None = None


class ContaSaida(EsquemaBase):
    nome: str
    email: str
    prioridade: Prioridade
    tem_provedor: bool


class AgentePorDescricao(EsquemaBase):
    descricao: str = Field(min_length=1)


class AgenteConfigurado(EsquemaBase):
    nome: str = Field(min_length=1)
    funcao: str
    papel: str
    cor: str | None = None
    movimento: Movimento | None = None
    ferramentas: list[str] = Field(default_factory=list)


AgenteCriacao = Annotated[AgentePorDescricao | AgenteConfigurado, Field(union_mode="left_to_right")]


class AgenteAtualizacao(EsquemaBase):
    nome: str | None = None
    funcao: str | None = None
    papel: str | None = None
    cor: str | None = None
    movimento: Movimento | None = None
    modelo_padrao: str | None = None


class AgenteSaida(EsquemaBase):
    id: UUID
    tipo: TipoAgente
    nome: str
    funcao: str
    cor: str
    movimento: Movimento
    status: str | None = None


class ConversaCriacao(EsquemaBase):
    agente_id: UUID | None = None
    texto: str
    anexos: list[UUID] = Field(default_factory=list)


class ConversaSaida(EsquemaBase):
    id: UUID
    agente_id: UUID
    tipo: TipoConversa
    titulo: str | None
    aprovada_versao: int | None
    criada_em: datetime
    atualizada_em: datetime


class RenomearConversaEntrada(EsquemaBase):
    titulo: str = Field(min_length=1)


class MensagemCriacao(EsquemaBase):
    texto: str
    anexos: list[UUID] = Field(default_factory=list)
    para_agente_id: UUID | None = None


class MensagemAceita(EsquemaBase):
    mensagem_id: UUID


class MensagemSaida(EsquemaBase):
    id: UUID
    conversa_id: UUID
    autor: AutorMensagem
    agente_id: UUID | None = None
    conteudo: str
    anexos: list[Any] = Field(default_factory=list)
    responde_a: UUID | None = None
    criada_em: datetime


class AjusteEntrada(EsquemaBase):
    texto: str
    agente_id: UUID | None = None


class AprovacaoVersaoEntrada(EsquemaBase):
    versao: int = Field(ge=1)


class RespostaPerguntaEntrada(EsquemaBase):
    valor: str


class DecisaoAprovacaoEntrada(EsquemaBase):
    decisao: DecisaoAprovacao


class ApagarContaEntrada(EsquemaBase):
    senha: str


class ProvedorCriacao(EsquemaBase):
    tipo: TipoProvedor
    chave: str | None = None
    base_url: str | None = None


class ProvedorAtualizacao(EsquemaBase):
    chave: str | None = None
    teto_mensal_usd: Decimal | None = None


class ProvedorSaida(EsquemaBase):
    id: UUID
    tipo: TipoProvedor
    base_url: str | None
    chave_final: str | None
    teto_mensal_usd: Decimal | None
    gasto_mes_usd: Decimal = Decimal("0")


class ProvedorConexaoSaida(EsquemaBase):
    provedor: ProvedorSaida
    modelos: list["ModeloSaida"]


class ModeloAtualizacao(EsquemaBase):
    nivel: str | None = None
    ativo: bool | None = None


class ModeloSaida(EsquemaBase):
    id: UUID
    provedor_id: UUID
    modelo: str
    nivel: str
    capacidades: list[str]
    contexto: int
    preco_entrada: Decimal | None
    preco_saida: Decimal | None
    velocidade_tps: int | None
    ativo: bool


class PreferenciasAtualizacao(EsquemaBase):
    prioridade: Prioridade


class EntregaSaida(EsquemaBase):
    id: UUID
    agente_id: UUID | None
    versao: int
    tipo: TipoEntrega
    titulo: str
    resumo: str
    conteudo: dict[str, Any]


class EntregasListaSaida(EsquemaBase):
    entregas: list[EntregaSaida]
    versoes: list[int]


class CadeiaSaida(EsquemaBase):
    id: UUID
    status: StatusCadeia
    plano: dict[str, Any] | None = None
    etapas: list[dict[str, Any]] = Field(default_factory=list)
    passos: list[dict[str, Any]] = Field(default_factory=list)
    modelos: list[str] = Field(default_factory=list)
    tokens_usados: int
    custo_usd: float


class UsoItem(EsquemaBase):
    data: datetime | None = None
    papel: str | None = None
    provedor: str | None = None
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_usd: float = 0.0


class UsoSaida(EsquemaBase):
    itens: list[UsoItem] = Field(default_factory=list)
    custo_total_usd: float = 0.0


class AnexoSaida(EsquemaBase):
    anexo_id: UUID
    nome: str
    tipo: str
    tamanho: int
