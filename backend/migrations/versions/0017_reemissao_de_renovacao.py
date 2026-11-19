"""Sessões contam as reemissões a partir do mesmo token anterior (F5 seguidos não derrubam login).

Antes, depois de 30 s o token anterior virava "reuso" e revogava a sessão: três recarregamentos
com a resposta da renovação perdida derrubavam o login (decisão 6 do Heitor). Agora, até 5 min e
no máximo 3 vezes, o anterior ganha um par novo; ``reemissoes`` guarda quantas vezes isso já
aconteceu desde a última rotação normal.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessoes", sa.Column("reemissoes", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    op.drop_column("sessoes", "reemissoes")
