"""Janela deslizante de limites no Redis; especificação §8.2."""

import pytest
from fakeredis import FakeAsyncRedis

from app.core.redis import verificar_limite


@pytest.fixture
async def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


async def test_libera_ate_o_limite_e_depois_devolve_retry_after(redis: FakeAsyncRedis) -> None:
    for i in range(5):
        assert await verificar_limite(redis, "login:a", 5, 900, agora=1000.0 + i) == 0
    # a mais antiga (1000) sai da janela em 1900; faltam 890 s a partir de 1010 (+1 de folga)
    assert await verificar_limite(redis, "login:a", 5, 900, agora=1010.0) == 891


async def test_a_janela_desliza_e_libera_de_novo(redis: FakeAsyncRedis) -> None:
    for i in range(5):
        await verificar_limite(redis, "login:a", 5, 900, agora=1000.0 + i)
    assert await verificar_limite(redis, "login:a", 5, 900, agora=1901.0) == 0


async def test_chaves_independentes(redis: FakeAsyncRedis) -> None:
    for _ in range(5):
        await verificar_limite(redis, "login:a", 5, 900, agora=1000.0)
    assert await verificar_limite(redis, "login:a", 5, 900, agora=1001.0) > 0
    assert await verificar_limite(redis, "login:b", 5, 900, agora=1001.0) == 0


async def test_tentativa_bloqueada_nao_conta(redis: FakeAsyncRedis) -> None:
    for _ in range(2):
        await verificar_limite(redis, "k", 2, 60, agora=100.0)
    for _ in range(10):
        assert await verificar_limite(redis, "k", 2, 60, agora=101.0) > 0
    assert await verificar_limite(redis, "k", 2, 60, agora=161.0) == 0
