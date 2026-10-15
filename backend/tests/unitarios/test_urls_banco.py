"""Uma DATABASE_URL só, com o driver certo para cada uso; especificação §8.3."""

import pytest

from app.core.config import url_pg_dump, url_psycopg, url_sqlalchemy

ENTRADAS = [
    "postgresql://u:p@db:5432/sora",
    "postgres://u:p@db:5432/sora",
    "postgresql+asyncpg://u:p@db:5432/sora",
    "postgresql+psycopg://u:p@db:5432/sora",
]


@pytest.mark.parametrize("entrada", ENTRADAS)
def test_cada_uso_recebe_o_driver_certo(entrada: str) -> None:
    assert url_sqlalchemy(entrada) == "postgresql+asyncpg://u:p@db:5432/sora"
    assert url_psycopg(entrada) == "postgresql://u:p@db:5432/sora"
    assert url_pg_dump(entrada) == "postgresql://u:p@db:5432/sora"


def test_url_que_nao_e_postgres_e_recusada() -> None:
    with pytest.raises(ValueError):
        url_sqlalchemy("mysql://u:p@db/sora")


def test_configuracao_expoe_as_tres_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Configuracao

    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@db/sora")
    config = Configuracao()  # type: ignore[call-arg]
    assert config.database_url_sqlalchemy.startswith("postgresql+asyncpg://")
    assert config.database_url_psycopg.startswith("postgresql://")
    assert config.database_url_pg_dump.startswith("postgresql://")
