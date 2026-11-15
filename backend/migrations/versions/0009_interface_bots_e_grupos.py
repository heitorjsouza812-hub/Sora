"""Interface de bots e grupos da etapa 5.

Revision ID: 0009i
Revises: 0008a
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009i"
down_revision = "0008a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("perguntas", sa.Column("grupo_id", sa.Uuid(), nullable=True))
    op.add_column(
        "perguntas",
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_foreign_key("perguntas_grupo_id_fkey", "perguntas", "canais_equipe", ["grupo_id"], ["id"])
    op.add_column("aprovacoes", sa.Column("grupo_id", sa.Uuid(), nullable=True))
    op.add_column(
        "aprovacoes",
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_foreign_key(
        "aprovacoes_grupo_id_fkey", "aprovacoes", "canais_equipe", ["grupo_id"], ["id"]
    )
    op.create_table(
        "rascunhos_bot",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("conversa_id", sa.Uuid(), sa.ForeignKey("conversas.id"), nullable=True),
        sa.Column("dados", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="rascunho"),
        sa.Column("agente_id", sa.Uuid(), sa.ForeignKey("agentes.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "propostas_grupo",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("conversa_id", sa.Uuid(), sa.ForeignKey("conversas.id"), nullable=True),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("pedido", sa.Text(), nullable=False),
        sa.Column(
            "bots_reaproveitados",
            postgresql.ARRAY(sa.Uuid()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("bots_novos", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.Text(), nullable=False, server_default="proposta"),
        sa.Column("grupo_id", sa.Uuid(), sa.ForeignKey("canais_equipe.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("propostas_grupo")
    op.drop_table("rascunhos_bot")
    op.drop_constraint("aprovacoes_grupo_id_fkey", "aprovacoes", type_="foreignkey")
    op.drop_column("aprovacoes", "criado_em")
    op.drop_column("aprovacoes", "grupo_id")
    op.drop_constraint("perguntas_grupo_id_fkey", "perguntas", type_="foreignkey")
    op.drop_column("perguntas", "criado_em")
    op.drop_column("perguntas", "grupo_id")
