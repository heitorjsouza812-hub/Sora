"""Biblioteca de arquivos: pastas, favorito e o índice da listagem por data."""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pastas_biblioteca",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ux_pastas_biblioteca_nome",
        "pastas_biblioteca",
        ["usuario_id", sa.text("lower(nome)")],
        unique=True,
    )
    op.add_column(
        "anexos",
        sa.Column(
            "pasta_id",
            sa.Uuid(),
            sa.ForeignKey("pastas_biblioteca.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "anexos", sa.Column("favorito", sa.Boolean(), nullable=False, server_default="false")
    )
    op.create_index("ix_anexos_usuario_criado", "anexos", ["usuario_id", "criado_em"])


def downgrade() -> None:
    op.drop_index("ix_anexos_usuario_criado", table_name="anexos")
    op.drop_column("anexos", "favorito")
    op.drop_column("anexos", "pasta_id")
    op.drop_index("ux_pastas_biblioteca_nome", table_name="pastas_biblioteca")
    op.drop_table("pastas_biblioteca")
