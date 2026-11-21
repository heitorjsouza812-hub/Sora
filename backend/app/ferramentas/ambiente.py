"""Apoio comum das ferramentas de coordenação: eventos, posse e correio das etapas.

As ferramentas só recebem o ``ContextoFerramenta``; aqui ficam o Redis dos eventos
(aberto na primeira necessidade, um por processo) e o correio da Sora para um
especialista em andamento (``mensagem_especialista``), que o worker esvazia antes de
cada chamada de modelo com ``ler_mensagens_pendentes``.
"""

from __future__ import annotations

import json
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


# ---------- mensagem para o turno em andamento (Onda 2, 2026-11-20) ----------
#
# Enquanto o worker roda o turno de uma conversa (Sora ou bot), a chave ``turno:vivo:<conversa>``
# existe. A API só aceita "mandar agora" com ela de pé, e a entrega é atômica (script Lua): ou a
# mensagem entra no correio do turno, ou a API manda pelo caminho normal. Antes de cada chamada
# de modelo, o middleware esvazia o correio e o texto entra no turno. O que sobrar quando o turno
# acaba (chegou depois da última chamada) vira mensagem normal na fila.

VALIDADE_TURNO_VIVO_SEGUNDOS = 15 * 60

_ENTREGAR_NO_TURNO = """
if redis.call('get', KEYS[1]) then
  redis.call('rpush', KEYS[2], ARGV[1])
  redis.call('expire', KEYS[2], tonumber(ARGV[2]))
  return 1
end
return 0
"""

_DESMARCAR_TURNO = """
if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end
return 0
"""


def chave_turno_vivo(conversa_id: UUID) -> str:
    return f"turno:vivo:{conversa_id}"


def chave_correio_turno(conversa_id: UUID) -> str:
    return f"turno:correio:{conversa_id}"


async def marcar_turno_vivo(conversa_id: UUID, marca: str, redis: Redis | None = None) -> None:
    await (redis or redis_dos_eventos()).set(
        chave_turno_vivo(conversa_id), marca, ex=VALIDADE_TURNO_VIVO_SEGUNDOS
    )


async def desmarcar_turno_vivo(conversa_id: UUID, marca: str, redis: Redis | None = None) -> None:
    """Só apaga a marca se ainda for deste turno (outro pode ter começado depois)."""
    await (redis or redis_dos_eventos()).eval(
        _DESMARCAR_TURNO, 1, chave_turno_vivo(conversa_id), marca
    )


async def entregar_no_turno(
    conversa_id: UUID, mensagem_id: UUID, texto: str, redis: Redis | None = None
) -> bool:
    """Põe a mensagem no correio do turno em andamento. ``False`` = não há turno rodando."""
    item = json.dumps({"mensagem_id": str(mensagem_id), "texto": texto}, ensure_ascii=False)
    entregue = await (redis or redis_dos_eventos()).eval(
        _ENTREGAR_NO_TURNO,
        2,
        chave_turno_vivo(conversa_id),
        chave_correio_turno(conversa_id),
        item,
        VALIDADE_CORREIO_SEGUNDOS,
    )
    return bool(entregue)


async def esvaziar_correio_do_turno(
    conversa_id: UUID, redis: Redis | None = None
) -> list[dict[str, str]]:
    """Esvazia e devolve o correio do turno (``mensagem_id`` e ``texto``), em ordem."""
    redis = redis or redis_dos_eventos()
    chave = chave_correio_turno(conversa_id)
    pipe = redis.pipeline(transaction=True)
    pipe.lrange(chave, 0, -1)
    pipe.delete(chave)
    itens, _ = await pipe.execute()
    saida: list[dict[str, str]] = []
    for bruto in itens:
        try:
            item = json.loads(bruto.decode() if isinstance(bruto, bytes) else bruto)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("texto"):
            saida.append({"mensagem_id": str(item.get("mensagem_id", "")), "texto": item["texto"]})
    return saida


async def ler_mensagens_do_turno(conversa_id: UUID) -> list[str]:
    """Para o middleware: só os textos."""
    return [item["texto"] for item in await esvaziar_correio_do_turno(conversa_id)]


async def ler_mensagens_pendentes(etapa_id: UUID) -> list[str]:
    """Esvazia e devolve as correções de rota da Sora, da mais antiga para a mais nova."""
    redis = redis_dos_eventos()
    chave = chave_do_correio(etapa_id)
    pipe = redis.pipeline(transaction=True)
    pipe.lrange(chave, 0, -1)
    pipe.delete(chave)
    itens, _ = await pipe.execute()
    return [i.decode() if isinstance(i, bytes) else i for i in itens]
