"""Ativa uma vez os modelos dos provedores já conectados; escolhas futuras são preservadas."""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE modelos_disponiveis SET ativo = true WHERE provedor_id IN "
        "(SELECT id FROM provedores WHERE apagado_em IS NULL)"
    )


def downgrade() -> None:
    # Não é possível reconstruir quais modelos estavam desligados antes da migração.
    pass
