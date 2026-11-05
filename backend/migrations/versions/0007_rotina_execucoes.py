"""Histórico das execuções de rotina (Relógio, etapa 4).

Revision ID: 0007r
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007r"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rotina_execucoes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rotina_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rotinas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuarios.id"),
            nullable=False,
        ),
        sa.Column(
            "iniciada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("concluida_em", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text(), server_default="executando", nullable=False),
        sa.Column("resumo", sa.Text()),
        sa.Column("erro", sa.Text()),
        sa.Column(
            "mensagem_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mensagens.id", ondelete="SET NULL"),
        ),
    )
    op.create_index(
        "ix_rotina_execucoes_rotina_id_iniciada_em",
        "rotina_execucoes",
        ["rotina_id", "iniciada_em"],
    )


def downgrade() -> None:
    op.drop_index("ix_rotina_execucoes_rotina_id_iniciada_em", table_name="rotina_execucoes")
    op.drop_table("rotina_execucoes")
