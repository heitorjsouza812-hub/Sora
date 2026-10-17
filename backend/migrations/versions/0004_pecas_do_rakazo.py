"""Peças adaptadas do Rakazo (docs/referencias/rakazo.md).

- ``conversas.resumo_compactado`` e ``conversas.compactado_ate``: compactação do histórico;
- ``mensagens.salto``: limite de saltos entre agentes;
- ``rotinas``: lembretes e pedidos agendados;
- ``pendencias``: trabalho aberto do agente;
- ``habilidades``: receitas SKILL.md;
- ``conectores``: servidores MCP do usuário (cabeçalhos cifrados);
- ``canais_vinculados``: chats do Telegram (e outros canais) ligados à conta.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), nullable=False)


def _agora(nome: str) -> sa.Column:
    return sa.Column(nome, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    op.add_column("conversas", sa.Column("resumo_compactado", sa.Text(), nullable=True))
    op.add_column("conversas", sa.Column("compactado_ate", sa.Integer(), nullable=True))
    op.add_column(
        "mensagens", sa.Column("salto", sa.Integer(), server_default="0", nullable=False)
    )

    op.create_table(
        "rotinas",
        _id(),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("agente_id", sa.Uuid(), nullable=False),
        sa.Column("conversa_id", sa.Uuid(), nullable=True),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("pedido", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("expressao", sa.Text(), nullable=True),
        sa.Column("fuso", sa.Text(), server_default="America/Sao_Paulo", nullable=False),
        sa.Column("proxima_execucao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultima_execucao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("silencioso", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("ativa", sa.Boolean(), server_default="true", nullable=False),
        _agora("criada_em"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["agente_id"], ["agentes.id"]),
        sa.ForeignKeyConstraint(["conversa_id"], ["conversas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rotinas_ativa_proxima_execucao", "rotinas", ["ativa", "proxima_execucao"]
    )

    op.create_table(
        "pendencias",
        _id(),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("agente_id", sa.Uuid(), nullable=False),
        sa.Column("titulo", sa.Text(), nullable=False),
        sa.Column("notas", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.Text(), server_default="aberta", nullable=False),
        _agora("criada_em"),
        _agora("atualizada_em"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["agente_id"], ["agentes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pendencias_agente_id_status", "pendencias", ["agente_id", "status"])

    op.create_table(
        "habilidades",
        _id(),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("origem", sa.Text(), server_default="usuario", nullable=False),
        _agora("criada_em"),
        _agora("atualizada_em"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "nome"),
    )

    op.create_table(
        "conectores",
        _id(),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("cabecalhos_cifrados", sa.LargeBinary(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        _agora("criado_em"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "nome"),
    )

    op.create_table(
        "canais_vinculados",
        _id(),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("canal", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        _agora("criado_em"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canal", "chat_id"),
    )


def downgrade() -> None:
    op.drop_table("canais_vinculados")
    op.drop_table("conectores")
    op.drop_table("habilidades")
    op.drop_index("ix_pendencias_agente_id_status", table_name="pendencias")
    op.drop_table("pendencias")
    op.drop_index("ix_rotinas_ativa_proxima_execucao", table_name="rotinas")
    op.drop_table("rotinas")
    op.drop_column("mensagens", "salto")
    op.drop_column("conversas", "compactado_ate")
    op.drop_column("conversas", "resumo_compactado")
