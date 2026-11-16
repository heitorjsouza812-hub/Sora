"""Seletor de modelo e permissão por conversa (Âncora-9): ``preferencias_conversa`` e o padrão
do bot (``agentes.provedor_padrao_id``, ``raciocinio_padrao``, ``permissao_padrao``)."""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agentes",
        sa.Column(
            "provedor_padrao_id",
            sa.Uuid(),
            sa.ForeignKey("provedores.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "agentes",
        sa.Column("raciocinio_padrao", sa.Text(), nullable=False, server_default="auto"),
    )
    op.add_column(
        "agentes",
        sa.Column("permissao_padrao", sa.Text(), nullable=False, server_default="perguntar"),
    )
    op.create_table(
        "preferencias_conversa",
        sa.Column("alvo_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "usuario_id",
            sa.Uuid(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column(
            "provedor_id",
            sa.Uuid(),
            sa.ForeignKey("provedores.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("modelo", sa.Text(), nullable=True),
        sa.Column("raciocinio", sa.Text(), nullable=False, server_default="auto"),
        sa.Column("permissao", sa.Text(), nullable=False, server_default="perguntar"),
        sa.Column(
            "atualizada_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("preferencias_conversa")
    op.drop_column("agentes", "permissao_padrao")
    op.drop_column("agentes", "raciocinio_padrao")
    op.drop_column("agentes", "provedor_padrao_id")
