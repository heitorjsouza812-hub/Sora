"""Apoio comum das ferramentas de coordenação: eventos, posse e correio das etapas.

As ferramentas só recebem o ``ContextoFerramenta``; aqui ficam o Redis dos eventos
(aberto na primeira necessidade, um por processo) e o correio da Sora para um
especialista em andamento (``mensagem_especialista``), que o worker esvazia antes de
cada chamada de modelo com ``ler_mensagens_pendentes``.
"""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import obter_configuracao
from app.core.redis import criar_cliente_redis
from app.eventos.streams import publicar_evento
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.modelos.tabelas import Cadeia, Etapa

VALIDADE_CORREIO_SEGUNDOS = 3600


@lru_cache
def redis_dos_eventos() -> Redis:
    return criar_cliente_redis(obter_configuracao().redis_url)


async def emitir(contexto: ContextoFerramenta, evento) -> None:
    """Publica o evento no stream da conversa (sempre depois do commit)."""
    await publicar_evento(redis_dos_eventos(), evento, contexto.conversa_id, contexto.usuario_id)


async def etapa_do_usuario(
    sessao: AsyncSession, contexto: ContextoFerramenta, etapa_id: UUID
) -> Etapa:
    """Etapa da cadeia do próprio usuário e da mesma conversa; senão, 'não encontrada'."""
    etapa = await sessao.scalar(
        select(Etapa)
        .join(Cadeia, Cadeia.id == Etapa.cadeia_id)
        .where(
            Etapa.id == etapa_id,
            Cadeia.usuario_id == contexto.usuario_id,
            Cadeia.conversa_id == contexto.conversa_id,
        )
    )
    if etapa is None:
        raise ErroFerramenta("Etapa não encontrada.")
    return etapa


def chave_do_correio(etapa_id: UUID) -> str:
    return f"correio:etapa:{etapa_id}"


async def guardar_mensagem(etapa_id: UUID, texto: str) -> None:
    redis = redis_dos_eventos()
    chave = chave_do_correio(etapa_id)
    await redis.rpush(chave, texto)
    await redis.expire(chave, VALIDADE_CORREIO_SEGUNDOS)


async def ler_mensagens_pendentes(etapa_id: UUID) -> list[str]:
    """Esvazia e devolve as correções de rota da Sora, da mais antiga para a mais nova."""
    redis = redis_dos_eventos()
    chave = chave_do_correio(etapa_id)
    pipe = redis.pipeline(transaction=True)
    pipe.lrange(chave, 0, -1)
    pipe.delete(chave)
    itens, _ = await pipe.execute()
    return [i.decode() if isinstance(i, bytes) else i for i in itens]
