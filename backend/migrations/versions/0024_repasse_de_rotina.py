"""Rotina que passa o resultado para outro bot (Onda 3, item 13).

``rotinas.seguinte_agente_id`` e ``seguinte_pedido``: quem recebe o resultado e o que faz com ele;
``seguinte_conversa_id``: a conversa do bot que recebe (criada na primeira vez).
``rotina_execucoes.repasse_*``: como foi o repasse daquela execução.
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rotinas",
        sa.Column(
            "seguinte_agente_id",
            sa.Uuid(),
            sa.ForeignKey("agentes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("rotinas", sa.Column("seguinte_pedido", sa.Text(), nullable=True))
    op.add_column(
        "rotinas",
        sa.Column(
            "seguinte_conversa_id",
            sa.Uuid(),
            sa.ForeignKey("conversas.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("rotina_execucoes", sa.Column("repasse_status", sa.Text(), nullable=True))
    op.add_column("rotina_execucoes", sa.Column("repasse_erro", sa.Text(), nullable=True))
    op.add_column(
        "rotina_execucoes",
        sa.Column(
            "repasse_mensagem_id",
            sa.Uuid(),
            sa.ForeignKey("mensagens.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("rotina_execucoes", "repasse_mensagem_id")
    op.drop_column("rotina_execucoes", "repasse_erro")
    op.drop_column("rotina_execucoes", "repasse_status")
    op.drop_column("rotinas", "seguinte_conversa_id")
    op.drop_column("rotinas", "seguinte_pedido")
    op.drop_column("rotinas", "seguinte_agente_id")
