"""A migração 0001 cria as mesmas tabelas, enums e índices do metadata; especificação §§1 e 8.3."""

import re
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.modelos import tabelas  # noqa: F401
from app.modelos.base import Base

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def sql_da_migracao() -> str:
    saida = StringIO()
    config = Config(str(RAIZ / "alembic.ini"), output_buffer=saida)
    config.set_main_option("script_location", str(RAIZ / "migrations"))
    config.set_main_option("sqlalchemy.url", "postgresql+asyncpg://u:p@localhost/db")
    command.upgrade(config, "head", sql=True)
    return saida.getvalue()


def test_mesmas_tabelas_do_metadata(sql_da_migracao: str) -> None:
    criadas = set(re.findall(r"CREATE TABLE (\w+) \(", sql_da_migracao)) - {"alembic_version"}
    assert criadas == set(Base.metadata.tables)


def test_mesmas_colunas_por_tabela(sql_da_migracao: str) -> None:
    for nome, tabela in Base.metadata.tables.items():
        corpo = re.search(rf"CREATE TABLE {nome} \((.*?)\n\);", sql_da_migracao, re.S)
        assert corpo, nome
        colunas = {
            linha.split()[0]
            for linha in corpo.group(1).splitlines()
            if linha.strip() and not linha.strip().startswith(("PRIMARY", "FOREIGN", "UNIQUE"))
        }
        colunas |= set(re.findall(rf"ALTER TABLE {nome} ADD COLUMN (\w+) ", sql_da_migracao))
        assert colunas == {c.name for c in tabela.columns}, nome


def test_enums_extensoes_e_indices(sql_da_migracao: str) -> None:
    assert "create extension if not exists pgcrypto" in sql_da_migracao
    assert "create extension if not exists vector" in sql_da_migracao
    for enum in ("status_etapa", "status_cadeia", "tipo_provedor", "prioridade"):
        assert f"CREATE TYPE {enum} AS ENUM" in sql_da_migracao
    assert "aguardando_usuario" in sql_da_migracao
    for tabela in Base.metadata.tables.values():
        for indice in tabela.indexes:
            assert re.search(rf"CREATE (UNIQUE )?INDEX {indice.name} ON", sql_da_migracao), (
                indice.name
            )
    assert "vector(768)" in sql_da_migracao
    assert "agentes_cadeia_id_fkey" in sql_da_migracao


def test_0002_acrescenta_colunas_de_rotulo_em_roteamentos(sql_da_migracao: str) -> None:
    for coluna in ("rotulo", "fonte_rotulo", "laya_saida", "laya_latencia_ms"):
        assert f"ALTER TABLE roteamentos ADD COLUMN {coluna} " in sql_da_migracao
        assert coluna in Base.metadata.tables["roteamentos"].columns


def test_metadata_cria_todas_as_tabelas_apesar_do_ciclo_de_chaves() -> None:
    import warnings

    from sqlalchemy import create_mock_engine

    comandos: list[str] = []
    motor = create_mock_engine(
        "postgresql+asyncpg://",
        lambda sql, *a, **k: comandos.append(str(sql.compile(dialect=motor.dialect))),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # ciclo sem use_alter vira aviso/erro de ordenação
        Base.metadata.create_all(motor, checkfirst=False)
    texto = " ".join(" ".join(comandos).split())
    assert "ALTER TABLE agentes ADD CONSTRAINT agentes_cadeia_id_fkey" in texto


def test_0003_indices_de_login_e_renovacao(sql_da_migracao: str) -> None:
    assert "CREATE UNIQUE INDEX ix_usuarios_email_minusculo ON usuarios (lower(email))" in (
        sql_da_migracao
    )
    assert "CREATE INDEX ix_sessoes_anterior_hash ON sessoes (anterior_hash)" in sql_da_migracao
    assert "CREATE INDEX ix_sessoes_usuario_id ON sessoes (usuario_id)" in sql_da_migracao
