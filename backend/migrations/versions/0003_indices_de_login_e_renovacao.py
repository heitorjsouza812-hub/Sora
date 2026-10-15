"""Índices das consultas de login e renovação; API-07/VAL-14.

- ``lower(email)`` em usuarios: login e cadastro comparam o e-mail em minúsculas.
- ``sessoes.anterior_hash``: a renovação procura o token atual OU o anterior.
- ``sessoes.usuario_id``: apagar conta e listar sessões do usuário.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_usuarios_email_minusculo", "usuarios", [sa.text("lower(email)")], unique=True
    )
    op.create_index("ix_sessoes_anterior_hash", "sessoes", ["anterior_hash"])
    op.create_index("ix_sessoes_usuario_id", "sessoes", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_sessoes_usuario_id", table_name="sessoes")
    op.drop_index("ix_sessoes_anterior_hash", table_name="sessoes")
    op.drop_index("ix_usuarios_email_minusculo", table_name="usuarios")
