"""Apagar conta (LGPD) cobre todas as tabelas, sem lista escrita à mão; especificação §8.2.

Antes, ``apagar_conta`` apagava ~21 tabelas listadas uma a uma. As tabelas das migrações 0004 em
diante (rotinas, habilidades, conectores, canais, navegador, rascunhos, canais da empresa…) ficaram
de fora e o ``DELETE FROM usuarios`` falhava por chave estrangeira para quem usou esses recursos.
"""

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.core import contas
from app.core.contas import TABELAS_SEM_DONO, condicoes_do_usuario
from app.modelos.base import Base


def test_apagar_conta_cobre_todas_as_tabelas() -> None:
    cobertas = {t.name for t in condicoes_do_usuario(uuid4())}
    todas = set(Base.metadata.tables) - TABELAS_SEM_DONO
    assert todas - cobertas == set(), (
        "tabela sem caminho até usuarios: apagar_conta deixaria dados para trás (ou falharia)"
    )


def test_fks_que_fecham_ciclo_podem_ser_zeradas() -> None:
    """As FKs com ``use_alter`` são zeradas antes de apagar: precisam aceitar NULL."""
    for tabela in Base.metadata.tables.values():
        for fk in tabela.foreign_keys:
            if contas._quebra_ciclo(fk):
                assert fk.parent.nullable, f"{tabela.name}.{fk.parent.name}"


def test_filhos_apagados_antes_dos_pais() -> None:
    """A ordem de exclusão é a inversa da dependência: nenhuma tabela é apagada antes de uma
    tabela que aponta para ela (fora das FKs de ciclo, que já foram zeradas)."""
    ordem = [t.name for t in reversed(list(condicoes_do_usuario(uuid4())))]
    posicao = {nome: i for i, nome in enumerate(ordem)}
    for tabela in Base.metadata.tables.values():
        if tabela.name not in posicao:
            continue
        for fk in tabela.foreign_keys:
            alvo = fk.column.table.name
            if contas._quebra_ciclo(fk) or alvo == tabela.name or alvo not in posicao:
                continue
            assert posicao[tabela.name] < posicao[alvo], f"{tabela.name} -> {alvo}"


def test_consultas_compilam_para_postgresql() -> None:
    from sqlalchemy import delete

    for tabela, condicao in condicoes_do_usuario(uuid4()).items():
        sql = str(delete(tabela).where(condicao).compile(dialect=postgresql.dialect()))
        assert sql.startswith(f"DELETE FROM {tabela.name}")


def test_tabelas_novas_das_etapas_4_a_6_entram() -> None:
    cobertas = {t.name for t in condicoes_do_usuario(uuid4())}
    for nome in (
        "rotinas",
        "habilidades",
        "conectores",
        "canais_equipe",
        "membros_canal",
        "mensagens_canal",
        "tarefas_canal",
        "fila_mensagens",
        "perfis_navegador",
        "abas_navegador",
        "rascunhos_bot",
        "propostas_grupo",
        "ce_conexoes",
        "ce_mensagens",
        "ce_fatos",
    ):
        assert nome in cobertas, nome
