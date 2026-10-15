"""Configuração do worker ARQ (especificação §6; serviço ``worker`` do
docker-compose em §8.3).

O ARQ tenta de novo até 3 vezes; a saída de cada chamada de modelo fica
salva por ``(etapa_id, tentativa)`` (checkpointer), então a retomada não paga
de novo o que já foi feito.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from app.busca.provedor import verificar_busca_permitida
from app.core.config import obter_configuracao
from app.llm.falso import verificar_modelo_falso_permitido
from workers.aprovacoes import expirar_aprovacao
from workers.cadeia import (
    ajustar,
    avancar_cadeia,
    entregar_resultado,
    executar_etapa,
    planejar_cadeia,
    verificar_cadeia,
)
from workers.conversa import responder_direto


def verificar_trava_de_producao() -> None:
    """Mesma trava do lifespan da API: o worker não sobe em produção com o modelo falso nem
    com uma busca só de desenvolvimento (``falso``, ``searxng``)."""
    config = obter_configuracao()
    verificar_modelo_falso_permitido(config.ambiente, config.sora_modelo_falso)
    verificar_busca_permitida(config.busca_provedor, config.ambiente)


async def ao_iniciar(ctx: dict[str, Any]) -> None:
    """Abre banco, Redis e o checkpointer do LangGraph e guarda no ``ctx``.

    Antes de tudo, a trava de produção (é o worker quem chama os modelos)."""
    verificar_trava_de_producao()
    raise NotImplementedError


async def ao_desligar(ctx: dict[str, Any]) -> None:
    """Fecha o que ``ao_iniciar`` abriu."""
    raise NotImplementedError


class WorkerSettings:
    """Lida pelo ``arq``; o Redis vem de ``REDIS_URL``."""

    redis_settings = RedisSettings.from_dsn(obter_configuracao().redis_url)

    functions: ClassVar[list[Any]] = [
        planejar_cadeia,
        avancar_cadeia,
        executar_etapa,
        verificar_cadeia,
        entregar_resultado,
        ajustar,
        responder_direto,
        expirar_aprovacao,
    ]
    on_startup = ao_iniciar
    on_shutdown = ao_desligar
    max_tries = 3
    job_timeout = 360
    """5 minutos da etapa + folga para gravar o erro."""
