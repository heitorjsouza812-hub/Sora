"""Catálogo de apps com login (Onda 3, item 12): o login OAuth de cada conector do catálogo.

``dados_cifrados`` guarda o cadastro do cliente, o endereço de token e os tokens, cifrados com a
chave mestra (AAD com o usuário e o conector). Apagar o conector apaga o login.
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conectores_oauth",
        sa.Column(
            "conector_id",
            sa.Uuid(),
            sa.ForeignKey("conectores.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("app", sa.Text(), nullable=False),
        sa.Column("dados_cifrados", sa.LargeBinary(), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("conectores_oauth")
