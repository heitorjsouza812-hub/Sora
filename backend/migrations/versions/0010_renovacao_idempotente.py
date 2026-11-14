"""Recuperação idempotente da renovação e detecção das gerações antigas."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009i"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessoes", sa.Column("anterior_rotacionado_em", sa.DateTime(timezone=True)))
    op.add_column("sessoes", sa.Column("par_atual_cifrado", sa.LargeBinary()))
    op.add_column(
        "sessoes",
        sa.Column("historico_hashes", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index(
        "ix_sessoes_historico_hashes", "sessoes", ["historico_hashes"], postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_sessoes_historico_hashes", table_name="sessoes")
    op.drop_column("sessoes", "historico_hashes")
    op.drop_column("sessoes", "par_atual_cifrado")
    op.drop_column("sessoes", "anterior_rotacionado_em")
