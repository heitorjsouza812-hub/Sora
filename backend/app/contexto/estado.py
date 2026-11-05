"""Estado do medidor de contexto no Redis (Âncora, etapa 4).

O ``MonitorContexto`` de ``app/contexto`` guarda o estado na memória do worker. Para a API
responder ``GET /v1/agentes/{id}/contexto`` e o medidor sobreviver a reiniciar o worker, cada
medição também vai para um hash no Redis (``contexto:<agente>``, um campo por fio) e para o
evento SSE ``contexto.atualizado``.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID

from app.contexto import (
    EstadoContexto,
    NivelContexto,
    SituacaoCompactacao,
)

PRAZO_S = 7 * 24 * 3600


def _chave(agente_id: UUID) -> str:
    return f"contexto:{agente_id}"


def _chave_turno(agente_id: UUID) -> str:
    return f"contexto-turno:{agente_id}"


def _para_json(estado: EstadoContexto) -> str:
    dados = asdict(estado)
    dados["agente_id"] = str(estado.agente_id)
    dados["nivel"] = estado.nivel.value
    dados["compactacao"] = estado.compactacao.value
    dados["medido_em"] = estado.medido_em.isoformat()
    return json.dumps(dados)


def _de_json(texto: str | bytes) -> EstadoContexto:
    dados: dict[str, Any] = json.loads(texto)
    return EstadoContexto(
        agente_id=UUID(dados["agente_id"]),
        fio=dados["fio"],
        tokens=int(dados["tokens"]),
        janela=int(dados["janela"]),
        estimado=bool(dados["estimado"]),
        nivel=NivelContexto(dados["nivel"]),
        compactacao=SituacaoCompactacao(dados["compactacao"]),
        medido_em=datetime.fromisoformat(dados["medido_em"]),
    )


async def gravar(redis: Any, estado: EstadoContexto) -> None:
    await redis.hset(_chave(estado.agente_id), estado.fio, _para_json(estado))
    await redis.expire(_chave(estado.agente_id), PRAZO_S)


async def ler(redis: Any, agente_id: UUID, fio: str = "principal") -> EstadoContexto | None:
    bruto = await redis.hget(_chave(agente_id), fio)
    return None if bruto is None else _de_json(bruto)


async def ler_todos(redis: Any, agente_id: UUID) -> list[EstadoContexto]:
    brutos = await redis.hgetall(_chave(agente_id))
    return sorted((_de_json(v) for v in brutos.values()), key=lambda e: e.fio)


async def marcar_turno(redis: Any, agente_id: UUID, rodando: bool) -> None:
    """O worker marca quando o agente está no meio de um turno (o botão não compacta nessa hora)."""
    if rodando:
        await redis.set(_chave_turno(agente_id), "1", ex=15 * 60)
    else:
        await redis.delete(_chave_turno(agente_id))


async def turno_rodando(redis: Any, agente_id: UUID) -> bool:
    return bool(await redis.exists(_chave_turno(agente_id)))


def evento_de(estado: EstadoContexto) -> Any:
    from app.eventos.equipe import ContextoAtualizado

    return ContextoAtualizado(
        agente_id=estado.agente_id,
        fio=estado.fio,
        porcentagem=estado.porcentagem,
        tokens=estado.tokens,
        janela=estado.janela,
        estimado=estado.estimado,
        nivel=estado.nivel.value,
        compactacao=estado.compactacao.value,
    )


async def registrar_e_publicar(
    redis: Any,
    estado: EstadoContexto,
    *,
    usuario_id: UUID,
    conversa_id: UUID,
    fim_da_compactacao: bool = False,
) -> EstadoContexto:
    """Guarda o estado, mantém a marca "compactando" até o fim e emite ``contexto.atualizado``."""
    from dataclasses import replace

    from app.eventos.streams import publicar_evento

    anterior = await ler(redis, estado.agente_id, estado.fio)
    if (
        not fim_da_compactacao
        and anterior is not None
        and anterior.compactacao is SituacaoCompactacao.COMPACTANDO
    ):
        estado = replace(estado, compactacao=SituacaoCompactacao.COMPACTANDO)
    await gravar(redis, estado)
    await publicar_evento(redis, evento_de(estado), conversa_id, usuario_id)
    return estado
