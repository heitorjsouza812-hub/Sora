""""Relatar problema": texto do usuário e diagnóstico do app, já mascarados.

O usuário pode retirar o relato (a linha é apagada). Apagar e exportar a conta pegam a tabela
sozinhos, pela chave estrangeira para ``usuarios``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relatos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("diagnostico", postgresql.JSONB(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_relatos_usuario_criado", "relatos", ["usuario_id", "criado_em"])


def downgrade() -> None:
    op.drop_index("ix_relatos_usuario_criado", table_name="relatos")
    op.drop_table("relatos")
