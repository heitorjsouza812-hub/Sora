"""Instruções próprias do agente (``propor_instrucoes``, Âncora, etapa 4).

Revision ID: 0008a
Revises: 0007r
"""

import sqlalchemy as sa
from alembic import op

revision = "0008a"
down_revision = "0007r"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agentes", sa.Column("instrucoes", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("agentes", "instrucoes")
