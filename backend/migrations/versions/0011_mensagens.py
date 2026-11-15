"""Estado, fontes e avaliação persistidos por mensagem."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mensagens", sa.Column("estado", sa.Text(), nullable=False, server_default="concluida")
    )
    op.add_column("mensagens", sa.Column("fontes", JSONB(), nullable=False, server_default="[]"))
    op.add_column("mensagens", sa.Column("avaliacao", sa.Integer()))
    op.create_check_constraint("ck_mensagens_avaliacao", "mensagens", "avaliacao IN (-1, 1)")


def downgrade() -> None:
    op.drop_constraint("ck_mensagens_avaliacao", "mensagens", type_="check")
    for campo in ("avaliacao", "fontes", "estado"):
        op.drop_column("mensagens", campo)
