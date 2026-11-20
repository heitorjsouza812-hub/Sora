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
from app.core.observabilidade import configurar_log, iniciar_sentry
from app.core.redis import criar_cliente_redis
from app.emails import criar_enviador
from app.llm.falso import verificar_modelo_falso_permitido
from workers.ancora import compactar_historico
from workers.aprovacoes import expirar_aprovacao
from workers.cadeia import (
    ajustar,
    avancar_cadeia,
    entregar_resultado,
    executar_etapa,
    planejar_cadeia,
    verificar_cadeia,
)
from workers.canais_empresa import (
    analisar_aprendizado_empresa,
    analisar_aprendizado_periodico,
    apagar_mensagens_vencidas,
    processar_canais_empresa,
    processar_pendentes_canais_empresa,
)
from workers.canal import responder_canal
from workers.computador import desligar_computador, desligar_computadores_ociosos
from workers.conversa import responder_direto, retomar_conversa
from workers.emails import enviar_link_de_senha_nova
from workers.equipe import (
    despachar_equipe,
    executar_item_fila,
    executar_tarefa_canal,
    recuperar_equipe_apos_queda,
    retomar_tarefa_canal,
)
from workers.fila import configurar_fila
from workers.navegador import abrir_aba_de_perfil, fechar_navegador, iniciar_navegador
from workers.rotinas import disparar_rotinas, executar_rotina
from workers.sessoes import apagar_sessoes_vencidas, limpar_pares_de_renovacao
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
    configurar_log()
    iniciar_sentry(config, "worker")
    ctx["sessoes"] = fabrica_sessoes()
    ctx["redis_eventos"] = criar_cliente_redis(config.redis_url)
    ctx["checkpointer"] = await abrir_checkpointer(config.database_url)
    ctx["email"] = criar_enviador(config)
    configurar_fila(ctx.get("redis"))
    await iniciar_navegador(ctx)
    await recuperar_equipe_apos_queda(ctx)


async def ao_desligar(ctx: dict[str, Any]) -> None:
    """Fecha o que ``ao_iniciar`` abriu."""
    configurar_fila(None)
    await fechar_navegador(ctx)
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
        responder_canal,
        abrir_aba_de_perfil,
        despachar_equipe,
        executar_item_fila,
        executar_tarefa_canal,
        retomar_tarefa_canal,
        desligar_computador,
        processar_canais_empresa,
        analisar_aprendizado_empresa,
        enviar_link_de_senha_nova,
    ]
    cron_jobs: ClassVar[list[Any]] = [
        cron(reconciliar_travados, second={0, 15, 30, 45}, run_at_startup=False),
        cron(disparar_rotinas, second={0, 10, 20, 30, 40, 50}, run_at_startup=True),
        cron(desligar_computadores_ociosos, second={5}, run_at_startup=False),
        cron(limpar_pares_de_renovacao, second={45}, run_at_startup=False),
        cron(apagar_sessoes_vencidas, hour={4}, minute={23}, second={0}),
        cron(processar_pendentes_canais_empresa, minute=set(range(0, 60, 5)), second={20}),
        cron(apagar_mensagens_vencidas, minute={17}, second={0}),
        cron(analisar_aprendizado_periodico, minute={42}, second={0}),
    ]
    on_startup = ao_iniciar
    on_shutdown = ao_desligar
    max_tries = 3
    max_jobs = obter_configuracao().worker_max_jobs
    job_timeout = 360
    """5 minutos da etapa + folga para gravar o erro."""
