"""Tabelas SQLAlchemy 2 da fase 1 e memória futura; especificação §§1 e 8.2."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.modelos.base import Base
from app.modelos.enumeracoes import (
    AutorMensagem,
    Movimento,
    OrigemMemoria,
    Prioridade,
    StatusAprovacao,
    StatusCadeia,
    StatusEtapa,
    TipoAgente,
    TipoConversa,
    TipoEntrega,
    TipoMemoria,
    TipoPasso,
    TipoProvedor,
)


class Vetor(UserDefinedType[Any]):
    """Tipo pgvector parametrizado pela dimensão do embedding."""

    cache_ok = True

    def __init__(self, dimensoes: int) -> None:
        self.dimensoes = dimensoes

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dimensoes})"


def enum_bd(tipo: type[Any], nome: str) -> Enum:
    """Cria um enum PostgreSQL com os valores textuais da especificação."""
    return Enum(tipo, name=nome, values_callable=lambda itens: [item.value for item in itens])


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True)
    nome: Mapped[str] = mapped_column(Text)
    idioma: Mapped[str] = mapped_column(Text, default="pt-BR", server_default="pt-BR")
    plano: Mapped[str] = mapped_column(Text, default="gratis", server_default="gratis")
    senha_hash: Mapped[str] = mapped_column(Text)
    email_verificado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prioridade: Mapped[Prioridade] = mapped_column(
        enum_bd(Prioridade, "prioridade"),
        default=Prioridade.CUSTO,
        server_default="custo",
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Login e cadastro procuram por lower(email): sem este índice a consulta varre a tabela.
Index("ix_usuarios_email_minusculo", func.lower(Usuario.email), unique=True)


class Agente(Base):
    __tablename__ = "agentes"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[TipoAgente] = mapped_column(enum_bd(TipoAgente, "tipo_agente"))
    nome: Mapped[str] = mapped_column(Text)
    funcao: Mapped[str] = mapped_column(Text, default="", server_default="")
    papel: Mapped[str] = mapped_column(Text, default="", server_default="")
    cor: Mapped[str] = mapped_column(Text, default="#E2ECFF", server_default="#E2ECFF")
    movimento: Mapped[Movimento] = mapped_column(
        enum_bd(Movimento, "movimento"), default=Movimento.GIRA, server_default="gira"
    )
    nivel_padrao: Mapped[str] = mapped_column(Text, default="N2", server_default="N2")
    modelo_padrao: Mapped[str | None] = mapped_column(Text)
    ferramentas: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )
    cadeia_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("cadeias.id", use_alter=True, name="agentes_cadeia_id_fkey")
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    apagado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversa(Base):
    __tablename__ = "conversas"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    agente_id: Mapped[UUID] = mapped_column(ForeignKey("agentes.id"))
    tipo: Mapped[TipoConversa] = mapped_column(
        enum_bd(TipoConversa, "tipo_conversa"),
        default=TipoConversa.CHAT,
        server_default="chat",
    )
    titulo: Mapped[str | None] = mapped_column(Text)
    aprovada_versao: Mapped[int | None]
    privada: Mapped[bool] = mapped_column(default=False, server_default="false")
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Mensagem(Base):
    __tablename__ = "mensagens"
    __table_args__ = (Index("ix_mensagens_conversa_id_criada_em", "conversa_id", "criada_em"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversa_id: Mapped[UUID] = mapped_column(ForeignKey("conversas.id"))
    autor: Mapped[AutorMensagem] = mapped_column(enum_bd(AutorMensagem, "autor_msg"))
    agente_id: Mapped[UUID | None] = mapped_column(ForeignKey("agentes.id"))
    conteudo: Mapped[str] = mapped_column(Text)
    anexos: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    visivel: Mapped[bool] = mapped_column(default=True, server_default="true")
    responde_a: Mapped[UUID | None] = mapped_column(ForeignKey("mensagens.id"))
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Roteamento(Base):
    __tablename__ = "roteamentos"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mensagem_id: Mapped[UUID] = mapped_column(ForeignKey("mensagens.id"))
    saida: Mapped[dict[str, Any]] = mapped_column(JSONB)
    modelo: Mapped[str] = mapped_column(Text)
    confianca: Mapped[float] = mapped_column(Float)
    escalou: Mapped[bool] = mapped_column(default=False, server_default="false")
    latencia_ms: Mapped[int]
    rotulo: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    fonte_rotulo: Mapped[str | None] = mapped_column(Text)
    laya_saida: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    laya_latencia_ms: Mapped[int | None]
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Cadeia(Base):
    __tablename__ = "cadeias"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    conversa_id: Mapped[UUID] = mapped_column(ForeignKey("conversas.id"))
    pedido_id: Mapped[UUID] = mapped_column(ForeignKey("mensagens.id"))
    status: Mapped[StatusCadeia] = mapped_column(
        enum_bd(StatusCadeia, "status_cadeia"),
        default=StatusCadeia.PLANEJANDO,
        server_default="planejando",
    )
    plano: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    versao: Mapped[int] = mapped_column(default=1, server_default="1")
    rodada: Mapped[int] = mapped_column(default=0, server_default="0")
    passos: Mapped[int] = mapped_column(default=0, server_default="0")
    orcamento_tokens: Mapped[int]
    tokens_usados: Mapped[int] = mapped_column(default=0, server_default="0")
    custo_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0, server_default="0")
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Etapa(Base):
    __tablename__ = "etapas"
    __table_args__ = (UniqueConstraint("cadeia_id", "ordem", "tentativa"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    cadeia_id: Mapped[UUID] = mapped_column(ForeignKey("cadeias.id"))
    ordem: Mapped[int]
    depende_de: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default=text("'{}'")
    )
    especialista: Mapped[str] = mapped_column(Text)
    agente_id: Mapped[UUID | None] = mapped_column(ForeignKey("agentes.id"))
    titulo: Mapped[str] = mapped_column(Text, default="", server_default="")
    nivel: Mapped[str] = mapped_column(Text)
    modelo: Mapped[str | None] = mapped_column(Text)
    tarefa: Mapped[str] = mapped_column(Text)
    saida: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[StatusEtapa] = mapped_column(
        enum_bd(StatusEtapa, "status_etapa"),
        default=StatusEtapa.PENDENTE,
        server_default="pendente",
    )
    tentativa: Mapped[int] = mapped_column(default=1, server_default="1")
    tokens: Mapped[int] = mapped_column(default=0, server_default="0")
    custo_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0, server_default="0")
    erro: Mapped[str | None] = mapped_column(Text)
    iniciada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Passo(Base):
    __tablename__ = "passos"
    __table_args__ = (Index("ix_passos_etapa_id_iniciado_em", "etapa_id", "iniciado_em"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    etapa_id: Mapped[UUID] = mapped_column(ForeignKey("etapas.id"))
    agente_id: Mapped[UUID] = mapped_column(ForeignKey("agentes.id"))
    tipo: Mapped[TipoPasso] = mapped_column(enum_bd(TipoPasso, "tipo_passo"))
    texto: Mapped[str] = mapped_column(Text)
    ferramenta: Mapped[str | None] = mapped_column(Text)
    acao: Mapped[str | None] = mapped_column(Text)
    parametros: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resultado: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    para_agente_id: Mapped[UUID | None] = mapped_column(ForeignKey("agentes.id"))
    status: Mapped[str] = mapped_column(Text, default="executando", server_default="executando")
    iniciado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Entrega(Base):
    __tablename__ = "entregas"
    __table_args__ = (Index("ix_entregas_conversa_id_versao", "conversa_id", "versao"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    conversa_id: Mapped[UUID] = mapped_column(ForeignKey("conversas.id"))
    cadeia_id: Mapped[UUID] = mapped_column(ForeignKey("cadeias.id"))
    etapa_id: Mapped[UUID | None] = mapped_column(ForeignKey("etapas.id"))
    agente_id: Mapped[UUID | None] = mapped_column(ForeignKey("agentes.id"))
    versao: Mapped[int]
    tipo: Mapped[TipoEntrega] = mapped_column(enum_bd(TipoEntrega, "tipo_entrega"))
    titulo: Mapped[str] = mapped_column(Text)
    resumo: Mapped[str] = mapped_column(Text)
    conteudo: Mapped[dict[str, Any] | list[Any] | str] = mapped_column(JSONB)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Anexo(Base):
    __tablename__ = "anexos"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    nome: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text)
    tamanho: Mapped[int]
    caminho: Mapped[str] = mapped_column(Text)
    origem: Mapped[str] = mapped_column(Text, default="usuario", server_default="usuario")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Provedor(Base):
    __tablename__ = "provedores"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[TipoProvedor] = mapped_column(enum_bd(TipoProvedor, "tipo_provedor"))
    base_url: Mapped[str | None] = mapped_column(Text)
    chave_cifrada: Mapped[bytes | None] = mapped_column(LargeBinary)
    chave_final: Mapped[str | None] = mapped_column(Text)
    teto_mensal_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    falhas_seguidas: Mapped[int] = mapped_column(default=0, server_default="0")
    pausado_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    apagado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModeloDisponivel(Base):
    __tablename__ = "modelos_disponiveis"
    __table_args__ = (UniqueConstraint("provedor_id", "modelo"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provedor_id: Mapped[UUID] = mapped_column(ForeignKey("provedores.id"))
    modelo: Mapped[str] = mapped_column(Text)
    nivel: Mapped[str] = mapped_column(Text)
    capacidades: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )
    contexto: Mapped[int]
    preco_entrada: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    preco_saida: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    velocidade_tps: Mapped[int | None]
    origem: Mapped[str] = mapped_column(Text, default="catalogo", server_default="catalogo")
    ativo: Mapped[bool] = mapped_column(default=True, server_default="true")


class ChamadaModelo(Base):
    __tablename__ = "chamadas_modelo"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    cadeia_id: Mapped[UUID | None] = mapped_column(ForeignKey("cadeias.id"))
    etapa_id: Mapped[UUID | None] = mapped_column(ForeignKey("etapas.id"))
    provedor_id: Mapped[UUID | None] = mapped_column(ForeignKey("provedores.id"))
    papel: Mapped[str] = mapped_column(Text)
    modelo: Mapped[str] = mapped_column(Text)
    nivel: Mapped[str] = mapped_column(Text)
    tokens_entrada: Mapped[int]
    tokens_saida: Mapped[int]
    custo_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    latencia_ms: Mapped[int]
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Pergunta(Base):
    __tablename__ = "perguntas"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversa_id: Mapped[UUID] = mapped_column(ForeignKey("conversas.id"))
    cadeia_id: Mapped[UUID | None] = mapped_column(ForeignKey("cadeias.id"))
    texto: Mapped[str] = mapped_column(Text)
    opcoes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    resposta_livre: Mapped[bool] = mapped_column(default=False, server_default="false")
    resposta: Mapped[str | None] = mapped_column(Text)
    respondida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Aprovacao(Base):
    __tablename__ = "aprovacoes"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    etapa_id: Mapped[UUID | None] = mapped_column(ForeignKey("etapas.id"))
    agente_id: Mapped[UUID] = mapped_column(ForeignKey("agentes.id"))
    acao: Mapped[dict[str, Any]] = mapped_column(JSONB)
    avaliacao: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[StatusAprovacao] = mapped_column(
        enum_bd(StatusAprovacao, "status_aprovacao"),
        default=StatusAprovacao.PENDENTE,
        server_default="pendente",
    )
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decidida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RegraPermissao(Base):
    __tablename__ = "regras_permissao"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    agente_id: Mapped[UUID | None] = mapped_column(ForeignKey("agentes.id"))
    ferramenta: Mapped[str] = mapped_column(Text)
    condicao: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegistroAcao(Base):
    __tablename__ = "registro_acoes"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    agente_id: Mapped[UUID] = mapped_column(ForeignKey("agentes.id"))
    etapa_id: Mapped[UUID | None] = mapped_column(ForeignKey("etapas.id"))
    ferramenta: Mapped[str] = mapped_column(Text)
    resumo: Mapped[str] = mapped_column(Text)
    aprovacao_id: Mapped[UUID | None] = mapped_column(ForeignKey("aprovacoes.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Evidencia(Base):
    __tablename__ = "evidencias"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    agente_id: Mapped[UUID | None] = mapped_column(ForeignKey("agentes.id"))
    pergunta: Mapped[str] = mapped_column(Text)
    resposta: Mapped[str] = mapped_column(Text)
    ocorreu_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processada: Mapped[bool] = mapped_column(default=False, server_default="false")


class Memoria(Base):
    __tablename__ = "memorias"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    agente_id: Mapped[UUID | None] = mapped_column(ForeignKey("agentes.id"))
    tipo: Mapped[TipoMemoria] = mapped_column(enum_bd(TipoMemoria, "tipo_memoria"))
    conteudo: Mapped[str] = mapped_column(String(500))
    origem: Mapped[OrigemMemoria] = mapped_column(enum_bd(OrigemMemoria, "origem_memoria"))
    travada: Mapped[bool] = mapped_column(default=False, server_default="false")
    evidencias: Mapped[list[UUID]] = mapped_column(
        ARRAY(Uuid(as_uuid=True)), default=list, server_default=text("'{}'")
    )
    data_referencia: Mapped[date | None] = mapped_column(Date)
    embedding: Mapped[Any | None] = mapped_column(Vetor(768))
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    apagada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Sessao(Base):
    __tablename__ = "sessoes"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    __table_args__ = (
        Index("ix_sessoes_anterior_hash", "anterior_hash"),
        Index("ix_sessoes_usuario_id", "usuario_id"),
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    anterior_hash: Mapped[str | None] = mapped_column(Text)
    cliente: Mapped[str] = mapped_column(Text, default="web", server_default="web")
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(INET)
    agente_usuario: Mapped[str | None] = mapped_column(Text)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Convite(Base):
    __tablename__ = "convites"
    codigo: Mapped[str] = mapped_column(Text, primary_key=True)
    usos_restantes: Mapped[int] = mapped_column(default=1, server_default="1")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TokenEmail(Base):
    __tablename__ = "tokens_email"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
