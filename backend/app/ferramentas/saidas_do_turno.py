"""Arquivos que o agente produziu e ainda não foram mostrados ao usuário.

``gerar_imagem`` e ``escrever_arquivo`` criam anexos; quem os leva ao usuário é a próxima mensagem
do mesmo agente (``falar`` no chat 1:1, ``canal_resultado`` no grupo). Antes, o modelo precisava
copiar o ``anexo_id`` do retorno da ferramenta para a mensagem, e quando esquecia a imagem ficava
guardada e invisível. Agora a ferramenta registra o anexo aqui e a mensagem seguinte o recolhe.

Fica no **Redis** (um conjunto ordenado por usuário e agente, nota = hora do registro), não na
memória do worker: se o worker reinicia no meio do turno, ou se a mensagem seguinte roda em outro
processo (retomada depois de aprovação ou pergunta), o anexo continua lá. O que não for recolhido
em ``VALIDADE_S`` (1 h) é esquecido (o arquivo continua guardado e acessível por id). Se o Redis
falhar, a mensagem sai sem os pendentes em vez de falhar.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from redis.asyncio import Redis

registro = logging.getLogger(__name__)

VALIDADE_S = 3600.0
MAX_POR_AGENTE = 10


def chave_das_saidas(usuario_id: UUID, agente_id: UUID) -> str:
    return f"saidas:{usuario_id}:{agente_id}"


def _redis(redis: Redis | None) -> Redis:
    if redis is not None:
        return redis
    from app.ferramentas.infra import obter_redis

    return obter_redis()


async def registrar(
    usuario_id: UUID, agente_id: UUID, anexo_id: UUID, *, redis: Redis | None = None
) -> None:
    """Marca ``anexo_id`` como produzido pelo agente e ainda não entregue."""
    chave = chave_das_saidas(usuario_id, agente_id)
    agora = time.time()
    try:
        cliente = _redis(redis)
        async with cliente.pipeline(transaction=True) as tubo:
            tubo.zremrangebyscore(chave, "-inf", agora - VALIDADE_S)
            tubo.zadd(chave, {str(anexo_id): agora})
            tubo.zremrangebyrank(chave, 0, -(MAX_POR_AGENTE + 1))
            tubo.expire(chave, int(VALIDADE_S))
            await tubo.execute()
    except Exception:
        registro.warning("não consegui registrar o anexo pendente %s", anexo_id, exc_info=True)


async def recolher(
    usuario_id: UUID,
    agente_id: UUID,
    explicitos: Iterable[UUID] = (),
    *,
    limite: int = 10,
    redis: Redis | None = None,
) -> list[UUID]:
    """Anexos da mensagem: os que o modelo indicou mais os pendentes, sem repetir, até ``limite``.
    Os pendentes saem do registro (cada arquivo é entregue uma vez)."""
    chave = chave_das_saidas(usuario_id, agente_id)
    pendentes: list[UUID] = []
    try:
        cliente = _redis(redis)
        async with cliente.pipeline(transaction=True) as tubo:
            tubo.zremrangebyscore(chave, "-inf", time.time() - VALIDADE_S)
            tubo.zrange(chave, 0, -1)
            tubo.delete(chave)
            _, valores, _ = await tubo.execute()
        for valor in valores:
            texto = valor.decode() if isinstance(valor, bytes) else valor
            try:
                pendentes.append(UUID(texto))
            except ValueError:
                continue
    except Exception:
        registro.warning("não consegui ler os anexos pendentes do agente", exc_info=True)
    return list(dict.fromkeys([*explicitos, *pendentes]))[:limite]
