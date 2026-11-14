"""Tabelas dos canais da empresa (migração 0012): conexões, contatos, mensagens lidas, ficha do
cliente, autorizações, base de conhecimento e sugestões de melhoria dos bots.

Importadas no fim de ``app/modelos/tabelas.py`` para entrarem no mesmo ``Base.metadata``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.modelos.base import Base


class ConexaoCanalEmpresa(Base):
    """Credenciais cifradas (AES-GCM, AAD ``usuario:canal_empresa:<canal>``) e canais lidos."""

    __tablename__ = "ce_conexoes"
    __table_args__ = (Index("ux_ce_conexoes_usuario_canal", "usuario_id", "canal", unique=True),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    canal: Mapped[str] = mapped_column(Text)  # slack | whatsapp
    rotulo: Mapped[str] = mapped_column(Text, default="", server_default="")
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    segredos: Mapped[bytes] = mapped_column(LargeBinary)
    canais_escolhidos: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    ativa: Mapped[bool] = mapped_column(default=True, server_default="true")
    ultimo_teste_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_teste_ok: Mapped[bool | None] = mapped_column()
    ultimo_teste_detalhe: Mapped[str | None] = mapped_column(Text)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PreferenciasCanaisEmpresa(Base):
    __tablename__ = "ce_preferencias"
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    retencao_dias: Mapped[int] = mapped_column(Integer, default=90, server_default="90")
    sugestoes_intervalo_dias: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    ultima_analise_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ContatoEmpresa(Base):
    __tablename__ = "ce_contatos"
    __table_args__ = (
        Index("ux_ce_contatos_conexao_externo", "conexao_id", "id_externo", unique=True),
        Index("ix_ce_contatos_usuario", "usuario_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    conexao_id: Mapped[UUID] = mapped_column(ForeignKey("ce_conexoes.id", ondelete="CASCADE"))
    canal: Mapped[str] = mapped_column(Text)
    id_externo: Mapped[str] = mapped_column(Text)  # telefone (WhatsApp) | usuário Slack
    nome: Mapped[str] = mapped_column(Text, default="", server_default="")
    papel: Mapped[str] = mapped_column(Text, default="cliente", server_default="cliente")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultima_mensagem_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MensagemEmpresa(Base):
    """Mensagem lida (já mascarada). ``texto`` some quando vence a retenção; a linha fica para
    a idempotência do webhook e para o link de origem dos fatos."""

    __tablename__ = "ce_mensagens"
    __table_args__ = (
        Index("ux_ce_mensagens_conexao_externo", "conexao_id", "id_externo", unique=True),
        Index("ix_ce_mensagens_contato", "contato_id", "enviada_em"),
        Index("ix_ce_mensagens_pendentes", "usuario_id", "processada_em"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    conexao_id: Mapped[UUID] = mapped_column(ForeignKey("ce_conexoes.id", ondelete="CASCADE"))
    contato_id: Mapped[UUID] = mapped_column(ForeignKey("ce_contatos.id", ondelete="CASCADE"))
    id_externo: Mapped[str] = mapped_column(Text)
    canal_externo: Mapped[str] = mapped_column(Text)  # canal do Slack | phone_number_id
    fio: Mapped[str] = mapped_column(Text)
    direcao: Mapped[str] = mapped_column(Text)  # entrada | saida (funcionário)
    texto: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    enviada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recebida_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    texto_apagado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FatoCliente(Base):
    """Um fato curto da ficha do cliente, com a mensagem de origem."""

    __tablename__ = "ce_fatos"
    __table_args__ = (Index("ix_ce_fatos_contato", "usuario_id", "contato_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    contato_id: Mapped[UUID] = mapped_column(ForeignKey("ce_contatos.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(Text)
    texto: Mapped[str] = mapped_column(String(300))
    data_referencia: Mapped[date | None] = mapped_column(Date)
    origem_canal: Mapped[str] = mapped_column(Text)
    origem_mensagem_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ce_mensagens.id", ondelete="SET NULL")
    )
    origem_externo_id: Mapped[str | None] = mapped_column(Text)
    origem_link: Mapped[str | None] = mapped_column(Text)
    editado: Mapped[bool] = mapped_column(default=False, server_default="false")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AutorizacaoEmpresa(Base):
    """Quem pode ver a ficha dos clientes e a base de conhecimento (bot ou grupo)."""

    __tablename__ = "ce_autorizacoes"
    __table_args__ = (
        Index("ux_ce_autorizacoes", "usuario_id", "alvo_tipo", "alvo_id", "escopo", unique=True),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    alvo_tipo: Mapped[str] = mapped_column(Text)  # agente | grupo
    alvo_id: Mapped[UUID] = mapped_column()
    escopo: Mapped[str] = mapped_column(Text)  # clientes | conhecimento
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConhecimentoEmpresa(Base):
    """Item da base de conhecimento da empresa (sem dado pessoal de cliente)."""

    __tablename__ = "ce_conhecimento"
    __table_args__ = (Index("ux_ce_conhecimento_chave", "usuario_id", "chave", unique=True),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    categoria: Mapped[str] = mapped_column(Text)
    chave: Mapped[str] = mapped_column(Text)
    titulo: Mapped[str] = mapped_column(String(200))
    conteudo: Mapped[str] = mapped_column(String(800))
    ocorrencias: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    contraditorio: Mapped[bool] = mapped_column(default=False, server_default="false")
    travado: Mapped[bool] = mapped_column(default=False, server_default="false")
    anteriores: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    origens: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    primeira_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ultima_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    apagado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SugestaoMelhoria(Base):
    """Sugestão da Sora para as instruções ou habilidades de um bot; só muda o bot no Aplicar."""

    __tablename__ = "ce_sugestoes"
    __table_args__ = (Index("ix_ce_sugestoes_usuario_status", "usuario_id", "status"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("usuarios.id"))
    agente_id: Mapped[UUID] = mapped_column(ForeignKey("agentes.id"))
    tipo: Mapped[str] = mapped_column(Text)  # instrucoes | habilidade
    titulo: Mapped[str] = mapped_column(String(200))
    motivo: Mapped[str] = mapped_column(String(500), default="", server_default="")
    texto: Mapped[str] = mapped_column(Text)
    habilidade_nome: Mapped[str | None] = mapped_column(Text)
    conhecimento_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(Text, default="pendente", server_default="pendente")
    chave: Mapped[str] = mapped_column(Text)
    aprovacao_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("aprovacoes.id", ondelete="SET NULL")
    )
    versao_anterior: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    versao_aplicada: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decidida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    desfeita_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
