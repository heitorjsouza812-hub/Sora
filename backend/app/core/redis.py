"""Define conexões Redis para fila, eventos e limites; especificação §§2 e 8.2."""

import time
import uuid

from redis.asyncio import Redis


def criar_cliente_redis(url: str) -> Redis:
    """Cria o cliente Redis assíncrono compartilhado pelo processo."""
    return Redis.from_url(url, decode_responses=True)


def _chave(chave: str) -> str:
    return f"limite:{chave}"


async def segundos_ate_liberar(
    redis: Redis, chave: str, limite: int, janela_segundos: int, *, agora: float | None = None
) -> int:
    """Só consulta a janela deslizante (não conta nada). 0 = liberado; senão, os segundos
    até liberar (valor do `Retry-After`)."""
    agora = time.time() if agora is None else agora
    chave_redis = _chave(chave)
    await redis.zremrangebyscore(chave_redis, 0, agora - janela_segundos)
    if await redis.zcard(chave_redis) < limite:
        return 0
    mais_antiga = await redis.zrange(chave_redis, 0, 0, withscores=True)
    liberar = mais_antiga[0][1] + janela_segundos - agora if mais_antiga else janela_segundos
    return max(1, int(liberar) + 1)


async def registrar_ocorrencia(
    redis: Redis, chave: str, janela_segundos: int, *, agora: float | None = None
) -> None:
    """Conta uma ocorrência na janela (ex.: uma senha errada)."""
    agora = time.time() if agora is None else agora
    chave_redis = _chave(chave)
    await redis.zadd(chave_redis, {f"{agora}:{uuid.uuid4().hex}": agora})
    await redis.expire(chave_redis, janela_segundos)


async def limpar_limite(redis: Redis, chave: str) -> None:
    """Zera a janela (ex.: login certo apaga as falhas daquele e-mail naquele IP)."""
    await redis.delete(_chave(chave))


async def reservar_vaga(
    redis: Redis, chave: str, limite: int, janela_segundos: int, *, agora: float | None = None
) -> tuple[int, str | None]:
    """Reserva uma vaga na janela de forma atômica (``MULTI``): grava a ocorrência e conta na
    mesma transação, então chamadas simultâneas nunca passam do limite (API-05).

    Devolve ``(0, membro)`` se coube (``membro`` serve para ``devolver_vaga``) ou
    ``(segundos até liberar, None)`` se estourou; nesse caso a ocorrência já foi desfeita.
    """
    agora = time.time() if agora is None else agora
    chave_redis = _chave(chave)
    membro = f"{agora}:{uuid.uuid4().hex}"
    async with redis.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(chave_redis, 0, agora - janela_segundos)
        pipe.zadd(chave_redis, {membro: agora})
        pipe.zcard(chave_redis)
        pipe.zrange(chave_redis, 0, 0, withscores=True)
        pipe.expire(chave_redis, janela_segundos)
        _, _, total, mais_antiga, _ = await pipe.execute()
    if total <= limite:
        return 0, membro
    await redis.zrem(chave_redis, membro)
    liberar = mais_antiga[0][1] + janela_segundos - agora if mais_antiga else janela_segundos
    return max(1, int(liberar) + 1), None


async def devolver_vaga(redis: Redis, chave: str, membro: str | None) -> None:
    """Desfaz uma reserva (ex.: o login deu certo, então a tentativa não conta como falha)."""
    if membro is not None:
        await redis.zrem(_chave(chave), membro)


async def verificar_limite(
    redis: Redis, chave: str, limite: int, janela_segundos: int, *, agora: float | None = None
) -> int:
    """Janela deslizante num sorted set. Devolve 0 se pode prosseguir (e conta a ação)
    ou os segundos até liberar (valor para o cabeçalho `Retry-After`). Atômico."""
    espera, _ = await reservar_vaga(redis, chave, limite, janela_segundos, agora=agora)
    return espera
