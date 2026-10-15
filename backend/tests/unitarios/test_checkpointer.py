"""Checkpointer do LangGraph (especificação §6.1): URL do psycopg e ciclo do pool.

Sem banco: o pool e o saver são trocados por falsos.
"""

from typing import Any, ClassVar
from uuid import UUID

import pytest

from app.agentes import checkpointer as cp


class PoolFalso:
    criados: ClassVar[list["PoolFalso"]] = []

    def __init__(self, conninfo: str, **opcoes: Any) -> None:
        self.conninfo = conninfo
        self.opcoes = opcoes
        self.aberto = False
        self.fechado = False
        PoolFalso.criados.append(self)

    async def open(self) -> None:
        self.aberto = True

    async def close(self) -> None:
        self.fechado = True


class SaverFalso:
    falhar = False

    def __init__(self, conn: PoolFalso) -> None:
        self.conn = conn
        self.preparado = False

    async def setup(self) -> None:
        if SaverFalso.falhar:
            raise RuntimeError("banco fora")
        self.preparado = True


@pytest.fixture(autouse=True)
def falsos(monkeypatch: pytest.MonkeyPatch) -> None:
    PoolFalso.criados = []
    SaverFalso.falhar = False
    monkeypatch.setattr(cp, "AsyncConnectionPool", PoolFalso)
    monkeypatch.setattr(cp, "AsyncPostgresSaver", SaverFalso)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://sora:segredo@postgres:5432/sora",
        "postgresql://sora:segredo@postgres:5432/sora",
    ],
)
async def test_usa_sempre_a_url_do_psycopg(url: str) -> None:
    saver = await cp.abrir_checkpointer(url)
    [pool] = PoolFalso.criados
    assert pool.conninfo == "postgresql://sora:segredo@postgres:5432/sora"
    assert pool.aberto and saver.preparado  # type: ignore[attr-defined]


async def test_pool_com_as_opcoes_que_o_saver_exige() -> None:
    await cp.abrir_checkpointer("postgresql+asyncpg://u:s@h/b", tamanho_do_pool=4)
    opcoes = PoolFalso.criados[0].opcoes
    assert opcoes["kwargs"]["autocommit"] is True
    assert opcoes["kwargs"]["prepare_threshold"] == 0
    assert opcoes["kwargs"]["row_factory"] is cp.dict_row
    assert opcoes["max_size"] == 4
    assert opcoes["open"] is False


async def test_setup_que_falha_fecha_o_pool() -> None:
    SaverFalso.falhar = True
    with pytest.raises(RuntimeError):
        await cp.abrir_checkpointer("postgresql://u:s@h/b")
    assert PoolFalso.criados[0].fechado


async def test_fechar_fecha_o_pool() -> None:
    saver = await cp.abrir_checkpointer("postgresql://u:s@h/b")
    await cp.fechar_checkpointer(saver)  # type: ignore[arg-type]
    assert PoolFalso.criados[0].fechado


def test_ids_de_thread() -> None:
    etapa = UUID("77777777-7777-4777-8777-777777777771")
    conversa = UUID("11111111-1111-4111-8111-111111111111")
    assert cp.thread_da_etapa(etapa) == f"etapa:{etapa}"
    assert cp.thread_da_conversa(conversa) == f"conversa:{conversa}"
