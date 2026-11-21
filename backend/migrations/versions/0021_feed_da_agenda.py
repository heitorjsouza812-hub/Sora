"""Feed ``.ics`` da agenda das rotinas: um endereço secreto por conta (só o hash no banco)."""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feeds_agenda",
        sa.Column(
            "usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), primary_key=True
        ),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("feeds_agenda")
