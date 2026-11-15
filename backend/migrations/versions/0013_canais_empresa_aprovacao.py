"""Canais da empresa: aprovação do conhecimento (estado, aprovado_em, em_disputa) e prazo de
retenção dos fatos da ficha (``ce_preferencias.retencao_fatos_dias``). Pedido da Ponte-2."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ce_conhecimento",
        sa.Column("estado", sa.Text(), nullable=False, server_default="pendente"),
    )
    op.add_column(
        "ce_conhecimento", sa.Column("aprovado_em", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "ce_conhecimento",
        sa.Column("em_disputa", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "ce_preferencias",
        sa.Column("retencao_fatos_dias", sa.Integer(), nullable=False, server_default="365"),
    )


def downgrade() -> None:
    op.drop_column("ce_preferencias", "retencao_fatos_dias")
    op.drop_column("ce_conhecimento", "em_disputa")
    op.drop_column("ce_conhecimento", "aprovado_em")
    op.drop_column("ce_conhecimento", "estado")
