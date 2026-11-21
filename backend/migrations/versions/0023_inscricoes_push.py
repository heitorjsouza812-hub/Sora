"""Web Push: aparelhos que recebem a notificação do "Precisa de você"."""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inscricoes_push",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("aparelho", sa.Text(), nullable=True),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("ultimo_envio_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_inscricoes_push_usuario", "inscricoes_push", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_inscricoes_push_usuario", table_name="inscricoes_push")
    op.drop_table("inscricoes_push")
