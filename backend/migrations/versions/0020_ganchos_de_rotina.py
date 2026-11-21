"""Webhook das rotinas e a origem de cada execução.

- ``ganchos_rotina``: um por rotina; rota secreta na URL e segredo de assinatura cifrado.
- ``entregas_gancho``: cada chamada recebida, sem o corpo (recusa repetidas e mostra histórico).
- ``rotina_execucoes.origem``: ``agenda``, ``manual`` ou ``webhook``.
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rotina_execucoes",
        sa.Column("origem", sa.Text(), nullable=False, server_default="agenda"),
    )
    op.create_table(
        "ganchos_rotina",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "rotina_id",
            sa.Uuid(),
            sa.ForeignKey("rotinas.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("rota", sa.Text(), nullable=False, unique=True),
        sa.Column("segredo_cifrado", sa.LargeBinary(), nullable=False),
        sa.Column(
            "tipos_evento",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("ultimo_recebido_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "entregas_gancho",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "gancho_id",
            sa.Uuid(),
            sa.ForeignKey("ganchos_rotina.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("mensagem_id", sa.Text(), nullable=False),
        sa.Column("tipo_evento", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("tamanho", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execucao_id", sa.Uuid(), nullable=True),
        sa.Column(
            "recebida_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("gancho_id", "mensagem_id"),
    )
    op.create_index(
        "ix_entregas_gancho_recebida", "entregas_gancho", ["gancho_id", "recebida_em"]
    )


def downgrade() -> None:
    op.drop_index("ix_entregas_gancho_recebida", table_name="entregas_gancho")
    op.drop_table("entregas_gancho")
    op.drop_table("ganchos_rotina")
    op.drop_column("rotina_execucoes", "origem")
