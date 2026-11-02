"""Ordem dos turnos das tarefas de canal por contador, não por horário.

- ``tarefas_canal.turno_seq``: turnos já iniciados (sobe em ``iniciar``);
- ``tarefas_canal.fim_no_turno_do_pai``: em que turno da mãe a filha terminou.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tarefas_canal", sa.Column("turno_seq", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "tarefas_canal",
        sa.Column("fim_no_turno_do_pai", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tarefas_canal", "fim_no_turno_do_pai")
    op.drop_column("tarefas_canal", "turno_seq")
