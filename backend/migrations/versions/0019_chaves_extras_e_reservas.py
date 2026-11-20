"""Chaves extras por conexão e modelos reserva da conta.

- ``chaves_provedor``: outras chaves da mesma conexão (mesmo provedor e URL). Quando a chave
  principal bate no limite, o mesmo modelo continua com a próxima. Cifradas como a principal.
- ``modelos_reserva``: até 3 modelos, em ordem, usados só quando o modelo escolhido no campo de
  mensagem falha (limite, fora do ar). A troca aparece na conversa.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chaves_provedor",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "provedor_id",
            sa.Uuid(),
            sa.ForeignKey("provedores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chave_cifrada", sa.LargeBinary(), nullable=False),
        sa.Column("chave_final", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_chaves_provedor_provedor", "chaves_provedor", ["provedor_id"])
    op.create_table(
        "modelos_reserva",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column(
            "provedor_id",
            sa.Uuid(),
            sa.ForeignKey("provedores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("modelo", sa.Text(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("usuario_id", "provedor_id", "modelo"),
    )


def downgrade() -> None:
    op.drop_table("modelos_reserva")
    op.drop_index("ix_chaves_provedor_provedor", table_name="chaves_provedor")
    op.drop_table("chaves_provedor")
