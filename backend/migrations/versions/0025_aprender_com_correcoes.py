"""Aprender com correções (Onda 3, item 15).

``usuarios.aprender_a_cada``: de quantas em quantas mensagens do usuário a Sora relê a conversa
(0 = desligado; padrão 20). ``conversas.aprendizado_ate``: até onde a conversa já foi relida.
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usuarios",
        sa.Column("aprender_a_cada", sa.Integer(), nullable=False, server_default="20"),
    )
    op.add_column(
        "conversas", sa.Column("aprendizado_ate", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("conversas", "aprendizado_ate")
    op.drop_column("usuarios", "aprender_a_cada")
