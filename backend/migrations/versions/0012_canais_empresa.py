"""Canais da empresa (Slack e WhatsApp só de leitura): contatos, mensagens, ficha do cliente,
autorizações, base de conhecimento e sugestões de melhoria dos bots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

AGORA = sa.text("now()")
VAZIO_OBJ = sa.text("'{}'::jsonb")
VAZIO_LISTA = sa.text("'[]'::jsonb")


def _tstz(nome: str, *, nulo: bool = True, agora: bool = False) -> sa.Column:
    return sa.Column(
        nome,
        sa.DateTime(timezone=True),
        nullable=nulo,
        server_default=AGORA if agora else None,
    )


def upgrade() -> None:
    op.create_table(
        "ce_conexoes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("canal", sa.Text(), nullable=False),
        sa.Column("rotulo", sa.Text(), nullable=False, server_default=""),
        sa.Column("config", JSONB(), nullable=False, server_default=VAZIO_OBJ),
        sa.Column("segredos", sa.LargeBinary(), nullable=False),
        sa.Column("canais_escolhidos", JSONB(), nullable=False, server_default=VAZIO_LISTA),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default="true"),
        _tstz("ultimo_teste_em"),
        sa.Column("ultimo_teste_ok", sa.Boolean()),
        sa.Column("ultimo_teste_detalhe", sa.Text()),
        _tstz("criada_em", nulo=False, agora=True),
        _tstz("atualizada_em", nulo=False, agora=True),
    )
    op.create_index(
        "ux_ce_conexoes_usuario_canal", "ce_conexoes", ["usuario_id", "canal"], unique=True
    )

    op.create_table(
        "ce_preferencias",
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), primary_key=True),
        sa.Column("retencao_dias", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("sugestoes_intervalo_dias", sa.Integer(), nullable=False, server_default="7"),
        _tstz("ultima_analise_em"),
        _tstz("atualizada_em", nulo=False, agora=True),
    )

    op.create_table(
        "ce_contatos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column(
            "conexao_id",
            sa.Uuid(),
            sa.ForeignKey("ce_conexoes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("canal", sa.Text(), nullable=False),
        sa.Column("id_externo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False, server_default=""),
        sa.Column("papel", sa.Text(), nullable=False, server_default="cliente"),
        _tstz("criado_em", nulo=False, agora=True),
        _tstz("ultima_mensagem_em"),
    )
    op.create_index(
        "ux_ce_contatos_conexao_externo", "ce_contatos", ["conexao_id", "id_externo"], unique=True
    )
    op.create_index("ix_ce_contatos_usuario", "ce_contatos", ["usuario_id"])

    op.create_table(
        "ce_mensagens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column(
            "conexao_id",
            sa.Uuid(),
            sa.ForeignKey("ce_conexoes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contato_id",
            sa.Uuid(),
            sa.ForeignKey("ce_contatos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("id_externo", sa.Text(), nullable=False),
        sa.Column("canal_externo", sa.Text(), nullable=False),
        sa.Column("fio", sa.Text(), nullable=False),
        sa.Column("direcao", sa.Text(), nullable=False),
        sa.Column("texto", sa.Text()),
        sa.Column("link", sa.Text()),
        _tstz("enviada_em", nulo=False),
        _tstz("recebida_em", nulo=False, agora=True),
        _tstz("processada_em"),
        _tstz("texto_apagado_em"),
    )
    op.create_index(
        "ux_ce_mensagens_conexao_externo",
        "ce_mensagens",
        ["conexao_id", "id_externo"],
        unique=True,
    )
    op.create_index("ix_ce_mensagens_contato", "ce_mensagens", ["contato_id", "enviada_em"])
    op.create_index("ix_ce_mensagens_pendentes", "ce_mensagens", ["usuario_id", "processada_em"])

    op.create_table(
        "ce_fatos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column(
            "contato_id",
            sa.Uuid(),
            sa.ForeignKey("ce_contatos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("texto", sa.String(300), nullable=False),
        sa.Column("data_referencia", sa.Date()),
        sa.Column("origem_canal", sa.Text(), nullable=False),
        sa.Column(
            "origem_mensagem_id",
            sa.Uuid(),
            sa.ForeignKey("ce_mensagens.id", ondelete="SET NULL"),
        ),
        sa.Column("origem_externo_id", sa.Text()),
        sa.Column("origem_link", sa.Text()),
        sa.Column("editado", sa.Boolean(), nullable=False, server_default="false"),
        _tstz("criado_em", nulo=False, agora=True),
        _tstz("atualizado_em", nulo=False, agora=True),
    )
    op.create_index("ix_ce_fatos_contato", "ce_fatos", ["usuario_id", "contato_id"])

    op.create_table(
        "ce_autorizacoes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("alvo_tipo", sa.Text(), nullable=False),
        sa.Column("alvo_id", sa.Uuid(), nullable=False),
        sa.Column("escopo", sa.Text(), nullable=False),
        _tstz("criada_em", nulo=False, agora=True),
    )
    op.create_index(
        "ux_ce_autorizacoes",
        "ce_autorizacoes",
        ["usuario_id", "alvo_tipo", "alvo_id", "escopo"],
        unique=True,
    )

    op.create_table(
        "ce_conhecimento",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("categoria", sa.Text(), nullable=False),
        sa.Column("chave", sa.Text(), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("conteudo", sa.String(800), nullable=False),
        sa.Column("ocorrencias", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("contraditorio", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("travado", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("anteriores", JSONB(), nullable=False, server_default=VAZIO_LISTA),
        sa.Column("origens", JSONB(), nullable=False, server_default=VAZIO_LISTA),
        _tstz("primeira_em", nulo=False, agora=True),
        _tstz("ultima_em", nulo=False, agora=True),
        _tstz("apagado_em"),
        _tstz("atualizado_em", nulo=False, agora=True),
    )
    op.create_index(
        "ux_ce_conhecimento_chave", "ce_conhecimento", ["usuario_id", "chave"], unique=True
    )

    op.create_table(
        "ce_sugestoes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("agente_id", sa.Uuid(), sa.ForeignKey("agentes.id"), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("motivo", sa.String(500), nullable=False, server_default=""),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("habilidade_nome", sa.Text()),
        sa.Column("conhecimento_ids", JSONB(), nullable=False, server_default=VAZIO_LISTA),
        sa.Column("status", sa.Text(), nullable=False, server_default="pendente"),
        sa.Column("chave", sa.Text(), nullable=False),
        sa.Column("aprovacao_id", sa.Uuid(), sa.ForeignKey("aprovacoes.id", ondelete="SET NULL")),
        sa.Column("versao_anterior", JSONB()),
        sa.Column("versao_aplicada", JSONB()),
        _tstz("criada_em", nulo=False, agora=True),
        _tstz("decidida_em"),
        _tstz("desfeita_em"),
    )
    op.create_index("ix_ce_sugestoes_usuario_status", "ce_sugestoes", ["usuario_id", "status"])


def downgrade() -> None:
    for tabela in (
        "ce_sugestoes",
        "ce_conhecimento",
        "ce_autorizacoes",
        "ce_fatos",
        "ce_mensagens",
        "ce_contatos",
        "ce_preferencias",
        "ce_conexoes",
    ):
        op.drop_table(tabela)
