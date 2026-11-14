"""Computador virtual dos bots no worker ARQ (Farol, C2; ``docs/computador-por-bot.md``).

- ``desligar_computadores_ociosos`` (cron, a cada minuto): desliga quem passou de
  ``COMPUTADOR_OCIOSO_SEGUNDOS`` sem uso. O último uso fica no Redis (``computador:uso``), então
  vale para todas as cópias do worker que falam com o mesmo host Docker;
- ``desligar_computador`` (job): a rota ``POST /v1/agentes/{id}/computador/desligar`` pede.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.computador.interface import Alvo
from app.computador.servico import CHAVE_USO, marcar_desligado

registro = logging.getLogger(__name__)


def _ultimo_uso(bruto: dict[Any, Any]) -> dict[UUID, float]:
    saida: dict[UUID, float] = {}
    for chave, valor in bruto.items():
        try:
            agente = UUID(chave.decode() if isinstance(chave, bytes) else str(chave))
            saida[agente] = float(valor.decode() if isinstance(valor, bytes) else valor)
        except ValueError:
            continue
    return saida


async def desligar_computadores_ociosos(ctx: dict[str, Any]) -> int:
    from app.computador.ferramentas import obter_servico
    from app.core.config import obter_configuracao

    config = obter_configuracao()
    if not config.sandbox_ativo:
        return 0
    servico = obter_servico()
    gerente = servico.provedores[Alvo.VIRTUAL]
    try:
        uso = _ultimo_uso(await servico.redis.hgetall(CHAVE_USO))
        desligados = await gerente.desligar_ociosos(uso, config.computador_ocioso_segundos)  # type: ignore[attr-defined]
    except Exception:
        registro.warning("não consegui desligar os computadores ociosos", exc_info=True)
        return 0
    for agente_id in desligados:
        servico.leituras.pop((agente_id, Alvo.VIRTUAL), None)
        await servico.redis.hdel(CHAVE_USO, str(agente_id))
        registro.info("computador do agente %s desligado por ociosidade", agente_id)
    return len(desligados)


async def desligar_computador(ctx: dict[str, Any], usuario_id: str, agente_id: str) -> bool:
    from app.computador.ferramentas import obter_servico
    from app.ferramentas.base import ErroFerramenta

    servico = obter_servico()
    agente, usuario = UUID(agente_id), UUID(usuario_id)
    try:
        desligado = await servico.provedores[Alvo.VIRTUAL].desligar(agente)
    except ErroFerramenta:  # sem Docker neste worker: nada ligado aqui
        desligado = False
    servico.leituras.pop((agente, Alvo.VIRTUAL), None)
    await marcar_desligado(servico.redis, servico.publicar, agente, usuario)
    return desligado
