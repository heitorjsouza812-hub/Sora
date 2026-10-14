"""Persistência e leitura dos Redis Streams de eventos; especificação §2.

Cada mudança vira uma entrada ``XADD`` no stream da conversa
(``eventos:{conversa_id}``), guardada por 24 horas. Os eventos de estado
(``TIPOS_EVENTOS_ESTADO``) também vão para ``eventos:usuario:{usuario_id}``,
com ``conversa_id`` dentro de ``data``. A leitura usa ``XREAD`` a partir do
``Last-Event-ID``, que é o id do próprio stream (string opaca para o app).

Formato de cada entrada no Redis: ``{"event": <nome>, "data": <json>}``.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.eventos.tipos import TIPOS_EVENTOS_ESTADO, Evento, EventoEstado

if TYPE_CHECKING:
    from redis.asyncio import Redis

RETENCAO_SEGUNDOS = 24 * 60 * 60
"""Quanto tempo um evento fica no stream (§2)."""

ID_DO_STREAM = re.compile(r"^\d+-\d+$")
INICIO_DO_STREAM = "0-0"


@dataclass(frozen=True, slots=True)
class EventoLido:
    """Uma entrada lida do stream, pronta para virar mensagem SSE."""

    id: str
    evento: str
    dados: dict[str, Any]


def canal_conversa(conversa_id: UUID) -> str:
    """Calcula o nome do stream durável de uma conversa."""
    return f"eventos:{conversa_id}"


def canal_usuario(usuario_id: UUID) -> str:
    """Calcula o nome do stream agregado de estado do usuário."""
    return f"eventos:usuario:{usuario_id}"


def eh_evento_de_estado(evento: Evento) -> bool:
    """Informa, pela lista central, se o evento também pertence ao canal do usuário."""
    return evento.evento in TIPOS_EVENTOS_ESTADO


def enriquecer_evento_do_usuario(evento: EventoEstado, conversa_id: UUID) -> dict[str, object]:
    """Representa o payload achatado do canal do usuário com sua conversa."""
    return {"conversa_id": str(conversa_id), **evento.model_dump(mode="json")}


def id_minimo_retido(agora_ms: int | None = None) -> str:
    """Id mais antigo que ainda deve ficar no stream (agora menos 24 horas)."""
    if agora_ms is None:
        agora_ms = int(time.time() * 1000)
    return f"{max(agora_ms - RETENCAO_SEGUNDOS * 1000, 0)}-0"


def id_valido(valor: str | None) -> bool:
    """Diz se o valor tem o formato de id do Redis Stream (``<ms>-<seq>``)."""
    return valor is not None and ID_DO_STREAM.match(valor) is not None


def _entrada(nome: str, dados: dict[str, object]) -> dict[str, str]:
    return {"event": nome, "data": json.dumps(dados, ensure_ascii=False, separators=(",", ":"))}


def _texto(valor: str | bytes) -> str:
    return valor.decode() if isinstance(valor, bytes) else valor


async def publicar_evento(redis: Redis, evento: Evento, conversa_id: UUID, usuario_id: UUID) -> str:
    """Grava o evento no stream da conversa (e no do usuário, se for de estado).

    Corta o que passou de 24 horas (``MINID``) e renova o prazo da chave, para
    um stream parado sumir sozinho. Devolve o id do stream da conversa, que é
    o ``id`` do SSE.
    """
    minimo = id_minimo_retido()
    canal = canal_conversa(conversa_id)
    pipe = redis.pipeline(transaction=False)
    pipe.xadd(
        canal,
        _entrada(evento.evento, evento.model_dump(mode="json")),
        minid=minimo,
        approximate=False,
    )
    pipe.expire(canal, RETENCAO_SEGUNDOS)
    if eh_evento_de_estado(evento):
        canal_u = canal_usuario(usuario_id)
        dados_u = enriquecer_evento_do_usuario(evento, conversa_id)  # type: ignore[arg-type]
        pipe.xadd(canal_u, _entrada(evento.evento, dados_u), minid=minimo, approximate=False)
        pipe.expire(canal_u, RETENCAO_SEGUNDOS)
    resultado = await pipe.execute()
    return _texto(resultado[0])


def _converter(id_bruto: str | bytes, campos: dict[Any, Any]) -> EventoLido:
    normalizados = {_texto(k): _texto(v) for k, v in campos.items()}
    return EventoLido(
        id=_texto(id_bruto), evento=normalizados["event"], dados=json.loads(normalizados["data"])
    )


async def ultimo_id(redis: Redis, canal: str) -> str:
    """Id da entrada mais nova do stream, ou ``0-0`` se ele estiver vazio."""
    entradas = await redis.xrevrange(canal, count=1)
    return _texto(entradas[0][0]) if entradas else INICIO_DO_STREAM


async def ponto_de_partida(redis: Redis, canal: str, ultimo_evento_id: str | None) -> str:
    """De onde começar a ler.

    Com um ``Last-Event-ID`` válido, continua dele. Sem ele (ou com um valor
    inválido), começa no fim do stream: o app já buscou o estado completo pela
    API antes de abrir o canal (§2), então só precisa do que vier depois.
    """
    if ultimo_evento_id is not None and id_valido(ultimo_evento_id):
        return ultimo_evento_id
    return await ultimo_id(redis, canal)


async def ler_lote(
    redis: Redis,
    canal: str,
    depois_de: str,
    *,
    bloquear_ms: int | None = None,
    limite: int = 100,
) -> list[EventoLido]:
    """Lê com ``XREAD`` as entradas depois de ``depois_de`` (exclusivo).

    Com ``bloquear_ms``, espera até esse tempo por uma entrada nova; devolve
    lista vazia quando nada chegou.
    """
    resposta = await redis.xread({canal: depois_de}, count=limite, block=bloquear_ms)
    if not resposta:
        return []
    _, entradas = resposta[0]
    return [_converter(id_bruto, campos) for id_bruto, campos in entradas]


async def ler_eventos(
    redis: Redis,
    canal: str,
    ultimo_evento_id: str | None,
    *,
    bloquear_ms: int = 15_000,
) -> AsyncIterator[EventoLido | None]:
    """Lê o stream sem parar, a partir do ``Last-Event-ID``.

    Entrega cada evento uma vez, na ordem. Quando ``bloquear_ms`` passa sem
    nada novo, entrega ``None`` (a hora do ``ping``).
    """
    cursor = await ponto_de_partida(redis, canal, ultimo_evento_id)
    while True:
        lote = await ler_lote(redis, canal, cursor, bloquear_ms=bloquear_ms)
        if not lote:
            yield None
            continue
        for evento in lote:
            cursor = evento.id
            yield evento
