"""Alinha criado_em ao modelo, preservando dados existentes."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    for tabela in ("rascunhos_bot", "propostas_grupo"):
        op.execute(sa.text(f"UPDATE {tabela} SET criado_em = now() WHERE criado_em IS NULL"))
        op.alter_column(tabela, "criado_em", nullable=False)


def downgrade():
    for tabela in ("rascunhos_bot", "propostas_grupo"):
        op.alter_column(tabela, "criado_em", nullable=True)
