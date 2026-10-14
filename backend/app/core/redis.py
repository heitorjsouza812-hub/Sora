"""Define conexões Redis para fila, eventos e limites; especificação §§2 e 8.2."""

import time
import uuid

from redis.asyncio import Redis


def criar_cliente_redis(url: str) -> Redis:
    """Cria o cliente Redis assíncrono compartilhado pelo processo."""
    return Redis.from_url(url, decode_responses=True)


async def verificar_limite(
    redis: Redis, chave: str, limite: int, janela_segundos: int, *, agora: float | None = None
) -> int:
    """Janela deslizante num sorted set. Devolve 0 se pode prosseguir (e conta a ação)
    ou os segundos até liberar (valor para o cabeçalho `Retry-After`)."""
    agora = time.time() if agora is None else agora
    chave_redis = f"limite:{chave}"
    await redis.zremrangebyscore(chave_redis, 0, agora - janela_segundos)
    if await redis.zcard(chave_redis) >= limite:
        mais_antiga = await redis.zrange(chave_redis, 0, 0, withscores=True)
        liberar = mais_antiga[0][1] + janela_segundos - agora if mais_antiga else janela_segundos
        return max(1, int(liberar) + 1)
    await redis.zadd(chave_redis, {f"{agora}:{uuid.uuid4().hex}": agora})
    await redis.expire(chave_redis, janela_segundos)
    return 0
