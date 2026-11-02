"""Configuração do worker ARQ (especificação §6; serviço ``worker`` do
docker-compose em §8.3).

O ARQ tenta de novo até 3 vezes; a saída de cada chamada de modelo fica
salva por ``(etapa_id, tentativa)`` (checkpointer), então a retomada não paga
de novo o que já foi feito.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.agentes.checkpointer import abrir_checkpointer, fechar_checkpointer
from app.busca.provedor import verificar_busca_permitida
from app.core.banco import fabrica_sessoes
from app.core.config import obter_configuracao
from app.core.redis import criar_cliente_redis
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
from workers.ancora import compactar_historico
from workers.conversa import responder_direto, retomar_conversa
from workers.fila import configurar_fila
from workers.rotinas import disparar_rotinas, executar_rotina
from workers.travados import reconciliar_travados


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
    config = obter_configuracao()
    ctx["sessoes"] = fabrica_sessoes()
    ctx["redis_eventos"] = criar_cliente_redis(config.redis_url)
    ctx["checkpointer"] = await abrir_checkpointer(config.database_url)
    configurar_fila(ctx.get("redis"))


async def ao_desligar(ctx: dict[str, Any]) -> None:
    """Fecha o que ``ao_iniciar`` abriu."""
    configurar_fila(None)
    checkpointer = ctx.pop("checkpointer", None)
    if checkpointer is not None:
        await fechar_checkpointer(checkpointer)
    redis_eventos = ctx.pop("redis_eventos", None)
    if redis_eventos is not None:
        await redis_eventos.aclose()


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
        retomar_conversa,
        expirar_aprovacao,
        reconciliar_travados,
        executar_rotina,
        compactar_historico,
    ]
    cron_jobs: ClassVar[list[Any]] = [
        cron(reconciliar_travados, second={0, 15, 30, 45}, run_at_startup=False),
        cron(disparar_rotinas, second={0, 10, 20, 30, 40, 50}, run_at_startup=True),
    ]
    on_startup = ao_iniciar
    on_shutdown = ao_desligar
    max_tries = 3
    job_timeout = 360
    """5 minutos da etapa + folga para gravar o erro."""
