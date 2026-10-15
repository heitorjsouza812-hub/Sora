"""Esquemas Pydantic dos contratos HTTP; especificação §§2, 5 e 8.2."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

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

# Limites de entrada (API-07, VAL-06/07): corpo gigante não chega ao argon2 nem vira prompt.
EMAIL_MAX = 254
SENHA_MAX = 256
NOME_MAX = 120
TEXTO_MAX = 20_000
CURTO_MAX = 2_000
URL_MAX = 2_048
TOKEN_MAX = 256
ANEXOS_MAX = 20

_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class EsquemaBase(BaseModel):
    """Base compatível com objetos ORM e nomes da API em PT-BR."""

    model_config = ConfigDict(from_attributes=True)


class CadastroEntrada(EsquemaBase):
    nome: str = Field(min_length=1, max_length=NOME_MAX)
    email: str = Field(max_length=EMAIL_MAX, pattern=_EMAIL)
    senha: str = Field(min_length=10, max_length=SENHA_MAX)
    convite: str | None = Field(default=None, max_length=TOKEN_MAX)


class LoginEntrada(EsquemaBase):
    email: str = Field(max_length=EMAIL_MAX)
    senha: str = Field(max_length=SENHA_MAX)


class RenovacaoEntrada(EsquemaBase):
    token_renovacao: str | None = Field(default=None, max_length=TOKEN_MAX)


class TokensSaida(EsquemaBase):
    token_acesso: str
    token_renovacao: str | None = None


class ContaSaida(EsquemaBase):
    nome: str
    email: str
    prioridade: Prioridade
    tem_provedor: bool


class AgentePorDescricao(EsquemaBase):
    descricao: str = Field(min_length=1, max_length=CURTO_MAX)


class AgenteConfigurado(EsquemaBase):
    nome: str = Field(min_length=1, max_length=NOME_MAX)
    funcao: str = Field(max_length=CURTO_MAX)
    papel: str = Field(max_length=CURTO_MAX)
    cor: str | None = Field(default=None, max_length=32)
    movimento: Movimento | None = None
    ferramentas: list[str] = Field(default_factory=list, max_length=50)


AgenteCriacao = Annotated[AgentePorDescricao | AgenteConfigurado, Field(union_mode="left_to_right")]


class AgenteAtualizacao(EsquemaBase):
    nome: str | None = Field(default=None, max_length=NOME_MAX)
    funcao: str | None = Field(default=None, max_length=CURTO_MAX)
    papel: str | None = Field(default=None, max_length=CURTO_MAX)
    cor: str | None = Field(default=None, max_length=32)
    movimento: Movimento | None = None
    modelo_padrao: str | None = Field(default=None, max_length=NOME_MAX)


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
    texto: str = Field(max_length=TEXTO_MAX)
    anexos: list[UUID] = Field(default_factory=list, max_length=ANEXOS_MAX)


class ConversaSaida(EsquemaBase):
    id: UUID
    agente_id: UUID
    tipo: TipoConversa
    titulo: str | None
    aprovada_versao: int | None
    criada_em: datetime
    atualizada_em: datetime


class RenomearConversaEntrada(EsquemaBase):
    titulo: str = Field(min_length=1, max_length=NOME_MAX)


class MensagemCriacao(EsquemaBase):
    texto: str = Field(max_length=TEXTO_MAX)
    anexos: list[UUID] = Field(default_factory=list, max_length=ANEXOS_MAX)
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
    texto: str = Field(max_length=TEXTO_MAX)
    agente_id: UUID | None = None


class AprovacaoVersaoEntrada(EsquemaBase):
    versao: int = Field(ge=1)


class RespostaPerguntaEntrada(EsquemaBase):
    valor: str = Field(max_length=CURTO_MAX)


class DecisaoAprovacaoEntrada(EsquemaBase):
    decisao: DecisaoAprovacao


class ApagarContaEntrada(EsquemaBase):
    senha: str = Field(max_length=SENHA_MAX)


class ProvedorCriacao(EsquemaBase):
    tipo: TipoProvedor
    chave: str | None = Field(default=None, max_length=CURTO_MAX)
    base_url: str | None = Field(default=None, max_length=URL_MAX)
    """Validada de novo em ``app.llm.provedores.validar_base_url`` (API-02)."""


class ProvedorAtualizacao(EsquemaBase):
    chave: str | None = Field(default=None, max_length=CURTO_MAX)
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
    conteudo: dict[str, Any] | list[Any] | str


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
    anexo_id: UUID = Field(validation_alias=AliasChoices("anexo_id", "id"))
    nome: str
    tipo: str
    tamanho: int
