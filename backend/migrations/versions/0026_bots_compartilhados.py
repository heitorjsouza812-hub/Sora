"""Compartilhar bot por link (Onda 3, item 16).

Um link ativo por bot. ``retrato`` é o que foi compartilhado no momento do link (nome, função,
cor, instruções, ferramentas, rotinas e habilidades escolhidas), nunca arquivos, memória,
conversas ou chaves; mudar o bot depois não muda o link. ``imagem`` é a prévia para redes sociais.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bots_compartilhados",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("usuario_id", sa.Uuid(), sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column(
            "agente_id",
            sa.Uuid(),
            sa.ForeignKey("agentes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("codigo", sa.Text(), nullable=False, unique=True),
        sa.Column("retrato", postgresql.JSONB(), nullable=False),
        sa.Column("imagem", sa.LargeBinary(), nullable=True),
        sa.Column("usos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_bots_compartilhados_agente_ativo",
        "bots_compartilhados",
        ["agente_id"],
        unique=True,
        postgresql_where=sa.text("revogado_em IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_bots_compartilhados_agente_ativo", table_name="bots_compartilhados")
    op.drop_table("bots_compartilhados")
