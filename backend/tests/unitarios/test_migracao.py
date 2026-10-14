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
        assert colunas == {c.name for c in tabela.columns}, nome


def test_enums_extensoes_e_indices(sql_da_migracao: str) -> None:
    assert "create extension if not exists pgcrypto" in sql_da_migracao
    assert "create extension if not exists vector" in sql_da_migracao
    for enum in ("status_etapa", "status_cadeia", "tipo_provedor", "prioridade"):
        assert f"CREATE TYPE {enum} AS ENUM" in sql_da_migracao
    assert "aguardando_usuario" in sql_da_migracao
    for tabela in Base.metadata.tables.values():
        for indice in tabela.indexes:
            assert f"CREATE INDEX {indice.name} ON" in sql_da_migracao
    assert "vector(768)" in sql_da_migracao
    assert "agentes_cadeia_id_fkey" in sql_da_migracao
