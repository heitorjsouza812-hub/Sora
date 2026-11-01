"""Peças inspiradas no OpenBot e escritas pela Sora (docs/referencias/openbot.md).

- ``agentes.fila_pausada``, ``agentes.limite_tarefas``: fila FIFO por agente (``app/filas``);
- ``agentes.perfil_navegador``, ``agentes.perfil_navegador_id``: perfil do navegador;
- ``fila_mensagens``: itens da fila, sobrevivem a quedas do worker;
- ``reacoes``: reações em mensagens (``app/correio/reacoes.py``);
- ``transferencias_arquivo``: arquivos passados entre agentes, com hash;
- ``canais_equipe``, ``membros_canal``, ``mensagens_canal``, ``tarefas_canal``: canais de equipe;
- ``perfis_navegador``, ``estados_navegador`` (cifrado), ``abas_navegador``: navegador persistente.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), nullable=False)


def _agora(nome: str) -> sa.Column:
    return sa.Column(nome, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def _lista_uuid(nome: str) -> sa.Column:
    return sa.Column(nome, sa.ARRAY(sa.Uuid()), server_default=sa.text("'{}'"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "perfis_navegador",
        _id(),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("cor", sa.Text(), nullable=False),
        _agora("criado_em"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "nome"),
    )

    op.add_column(
        "agentes", sa.Column("fila_pausada", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column(
        "agentes", sa.Column("limite_tarefas", sa.Integer(), server_default="2", nullable=False)
    )
    op.add_column(
        "agentes",
        sa.Column("perfil_navegador", sa.Text(), server_default="compartilhado", nullable=False),
    )
    op.add_column("agentes", sa.Column("perfil_navegador_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "agentes_perfil_navegador_id_fkey",
        "agentes",
        "perfis_navegador",
        ["perfil_navegador_id"],
        ["id"],
    )

    op.create_table(
        "fila_mensagens",
        _id(),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("agente_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("pista", sa.Text(), server_default="principal", nullable=False),
        sa.Column("origem", sa.Text(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        _lista_uuid("anexos"),
        sa.Column("de_agente_id", sa.Uuid(), nullable=True),
        sa.Column("responde_a", sa.Uuid(), nullable=True),
        sa.Column("salto", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chave", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="na_fila", nullable=False),
        sa.Column("em_edicao_por", sa.Text(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        _agora("criado_em"),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["agente_id"], ["agentes.id"]),
        sa.ForeignKeyConstraint(["de_agente_id"], ["agentes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agente_id", "seq"),
        sa.UniqueConstraint("agente_id", "chave"),
    )
    op.create_index(
        "ix_fila_mensagens_agente_id_status", "fila_mensagens", ["agente_id", "status"]
    )

    op.create_table(
        "reacoes",
        _id(),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("mensagem_id", sa.Uuid(), nullable=False),
        sa.Column("autor", sa.Text(), nullable=False),
        sa.Column("agente_id", sa.Uuid(), nullable=True),
        sa.Column("emoji", sa.Text(), nullable=False),
        _agora("criada_em"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["agente_id"], ["agentes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mensagem_id", "autor", "agente_id", "emoji", postgresql_nulls_not_distinct=True
        ),
    )

    op.create_table(
        "transferencias_arquivo",
        _id(),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("anexo_id", sa.Uuid(), nullable=False),
        sa.Column("de_agente_id", sa.Uuid(), nullable=False),
        sa.Column("para_agente_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("tamanho", sa.BigInteger(), nullable=False),
        sa.Column("imagem", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.Text(), server_default="pendente", nullable=False),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("novo_anexo_id", sa.Uuid(), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        _agora("criada_em"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["anexo_id"], ["anexos.id"]),
        sa.ForeignKeyConstraint(["de_agente_id"], ["agentes.id"]),
        sa.ForeignKeyConstraint(["para_agente_id"], ["agentes.id"]),
        sa.ForeignKeyConstraint(["novo_anexo_id"], ["anexos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transferencias_arquivo_para_agente_id", "transferencias_arquivo", ["para_agente_id"]
    )

    op.create_table(
        "canais_equipe",
        _id(),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("proposito", sa.Text(), server_default="", nullable=False),
        sa.Column("instrucoes", sa.Text(), server_default="", nullable=False),
        sa.Column("lider_id", sa.Uuid(), nullable=True),
        sa.Column("resumo", sa.Text(), nullable=True),
        sa.Column("resumo_ate_seq", sa.Integer(), nullable=True),
        _lista_uuid("pedidos_sem_lider"),
        sa.Column("arquivado_em", sa.DateTime(timezone=True), nullable=True),
        _agora("criado_em"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["lider_id"], ["agentes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "membros_canal",
        sa.Column("canal_id", sa.Uuid(), nullable=False),
        sa.Column("agente_id", sa.Uuid(), nullable=False),
        sa.Column("ordem", sa.Integer(), server_default="0", nullable=False),
        _agora("entrou_em"),
        sa.ForeignKeyConstraint(["canal_id"], ["canais_equipe.id"]),
        sa.ForeignKeyConstraint(["agente_id"], ["agentes.id"]),
        sa.PrimaryKeyConstraint("canal_id", "agente_id"),
    )

    op.create_table(
        "mensagens_canal",
        _id(),
        sa.Column("canal_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("autor", sa.Text(), nullable=False),
        sa.Column("agente_id", sa.Uuid(), nullable=True),
        sa.Column("tipo", sa.Text(), server_default="mensagem", nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("responde_a", sa.Uuid(), nullable=True),
        sa.Column("tarefa_id", sa.Uuid(), nullable=True),
        _lista_uuid("anexos"),
        _agora("criada_em"),
        sa.ForeignKeyConstraint(["canal_id"], ["canais_equipe.id"]),
        sa.ForeignKeyConstraint(["agente_id"], ["agentes.id"]),
        sa.ForeignKeyConstraint(["responde_a"], ["mensagens_canal.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canal_id", "seq"),
    )

    op.create_table(
        "tarefas_canal",
        _id(),
        sa.Column("canal_id", sa.Uuid(), nullable=False),
        sa.Column("pedido_id", sa.Uuid(), nullable=False),
        sa.Column("dono_id", sa.Uuid(), nullable=False),
        sa.Column("instrucao", sa.Text(), nullable=False),
        sa.Column("raiz_id", sa.Uuid(), nullable=False),
        sa.Column("pai_id", sa.Uuid(), nullable=True),
        sa.Column("delegada_por", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), server_default="na_fila", nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("revisao", sa.Integer(), server_default="1", nullable=False),
        _lista_uuid("seguimentos"),
        sa.Column("resultado", sa.Text(), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        _agora("criada_em"),
        _agora("atualizada_em"),
        sa.ForeignKeyConstraint(["canal_id"], ["canais_equipe.id"]),
        sa.ForeignKeyConstraint(["pedido_id"], ["mensagens_canal.id"]),
        sa.ForeignKeyConstraint(["dono_id"], ["agentes.id"]),
        sa.ForeignKeyConstraint(["pai_id"], ["tarefas_canal.id"]),
        sa.ForeignKeyConstraint(["delegada_por"], ["agentes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tarefas_canal_canal_id_status", "tarefas_canal", ["canal_id", "status"]
    )
    op.create_foreign_key(
        "mensagens_canal_tarefa_id_fkey",
        "mensagens_canal",
        "tarefas_canal",
        ["tarefa_id"],
        ["id"],
    )

    op.create_table(
        "estados_navegador",
        sa.Column("particao", sa.Text(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("estado_cifrado", sa.LargeBinary(), nullable=False),
        _agora("atualizado_em"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("particao"),
    )

    op.create_table(
        "abas_navegador",
        _id(),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("agente_id", sa.Uuid(), nullable=False),
        sa.Column("particao", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), server_default="about:blank", nullable=False),
        sa.Column("titulo", sa.Text(), server_default="", nullable=False),
        _agora("aberta_em"),
        _agora("usada_em"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["agente_id"], ["agentes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abas_navegador_agente_id", "abas_navegador", ["agente_id"])


def downgrade() -> None:
    op.drop_index("ix_abas_navegador_agente_id", table_name="abas_navegador")
    op.drop_table("abas_navegador")
    op.drop_table("estados_navegador")
    op.drop_constraint("mensagens_canal_tarefa_id_fkey", "mensagens_canal", type_="foreignkey")
    op.drop_index("ix_tarefas_canal_canal_id_status", table_name="tarefas_canal")
    op.drop_table("tarefas_canal")
    op.drop_table("mensagens_canal")
    op.drop_table("membros_canal")
    op.drop_table("canais_equipe")
    op.drop_index(
        "ix_transferencias_arquivo_para_agente_id", table_name="transferencias_arquivo"
    )
    op.drop_table("transferencias_arquivo")
    op.drop_table("reacoes")
    op.drop_index("ix_fila_mensagens_agente_id_status", table_name="fila_mensagens")
    op.drop_table("fila_mensagens")
    op.drop_constraint("agentes_perfil_navegador_id_fkey", "agentes", type_="foreignkey")
    op.drop_column("agentes", "perfil_navegador_id")
    op.drop_column("agentes", "perfil_navegador")
    op.drop_column("agentes", "limite_tarefas")
    op.drop_column("agentes", "fila_pausada")
    op.drop_table("perfis_navegador")
