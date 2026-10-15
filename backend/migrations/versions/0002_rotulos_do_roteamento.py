"""Colunas de rótulo e do Laya em roteamentos; especificação §7 ("Colunas novas").

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("roteamentos", sa.Column("rotulo", postgresql.JSONB(), nullable=True))
    op.add_column("roteamentos", sa.Column("fonte_rotulo", sa.Text(), nullable=True))
    op.add_column("roteamentos", sa.Column("laya_saida", postgresql.JSONB(), nullable=True))
    op.add_column("roteamentos", sa.Column("laya_latencia_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    for coluna in ("laya_latencia_ms", "laya_saida", "fonte_rotulo", "rotulo"):
        op.drop_column("roteamentos", coluna)
