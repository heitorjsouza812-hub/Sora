"""Define conexões Redis para fila, eventos e limites; especificação §§2 e 8.2."""

from redis.asyncio import Redis


def criar_cliente_redis(url: str) -> Redis:
    """Cria o cliente Redis assíncrono compartilhado pelo processo."""
    raise NotImplementedError


async def verificar_limite(chave: str, limite: int, janela_segundos: int) -> bool:
    """Verifica uma janela deslizante e informa se a ação pode prosseguir."""
    raise NotImplementedError
