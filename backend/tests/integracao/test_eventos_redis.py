"""Eventos num Redis de verdade (especificação §2 e §8.5).

Sobe um ``redis:7`` com testcontainers. Sem Docker, pula sozinho.
"""

from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.eventos.streams import (
    RETENCAO_SEGUNDOS,
    canal_conversa,
    canal_usuario,
    ler_lote,
    ponto_de_partida,
    publicar_evento,
)
from app.eventos.tipos import EtapaAtualizada, SugestoesEvento

pytestmark = pytest.mark.integracao


def _docker_disponivel() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


@pytest.fixture(scope="module")
def url_redis() -> Iterator[str]:
    if not _docker_disponivel():
        pytest.skip("Docker não está disponível")
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7") as conteiner:
        host = conteiner.get_container_host_ip()
        porta = conteiner.get_exposed_port(6379)
        yield f"redis://{host}:{porta}/0"


@pytest.fixture
async def redis(url_redis: str) -> AsyncIterator[Redis]:
    cliente = Redis.from_url(url_redis, decode_responses=True)
    yield cliente
    await cliente.flushdb()
    await cliente.aclose()


async def test_publicar_e_reconectar_sem_perder_nem_repetir(redis: Redis) -> None:
    conversa, usuario = uuid4(), uuid4()
    canal = canal_conversa(conversa)
    ids = [
        await publicar_evento(redis, SugestoesEvento(itens=[str(i)]), conversa, usuario)
        for i in range(5)
    ]

    inicio = await ponto_de_partida(redis, canal, ids[1])
    assert [e.id for e in await ler_lote(redis, canal, inicio)] == ids[2:]
    assert 0 < await redis.ttl(canal) <= RETENCAO_SEGUNDOS


async def test_evento_de_estado_vai_para_o_canal_do_usuario(redis: Redis) -> None:
    conversa, usuario = uuid4(), uuid4()
    etapa = EtapaAtualizada(
        etapa_id=uuid4(), status="executando", progresso=10, tokens=0, custo_usd=0.0
    )
    await publicar_evento(redis, etapa, conversa, usuario)

    [lido] = await ler_lote(redis, canal_usuario(usuario), "0-0")
    assert lido.dados["conversa_id"] == str(conversa)


async def test_xread_bloqueante_acorda_com_evento(redis: Redis) -> None:
    import asyncio

    conversa, usuario = uuid4(), uuid4()
    canal = canal_conversa(conversa)

    async def publicar_depois() -> str:
        await asyncio.sleep(0.1)
        return await publicar_evento(redis, SugestoesEvento(itens=["x"]), conversa, usuario)

    tarefa = asyncio.create_task(publicar_depois())
    lote = await ler_lote(redis, canal, "0-0", bloquear_ms=3_000)
    assert [e.id for e in lote] == [await tarefa]
