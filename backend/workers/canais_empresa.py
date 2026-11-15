"""Jobs dos canais da empresa (Ponte): resumo das mensagens lidas, retenção, análise semanal.

- ``processar_canais_empresa``: enfileirado pelo webhook (adiado ~60 s para juntar a conversa).
- ``processar_pendentes_canais_empresa`` (cron, 5 min): rede de segurança; pega o que sobrou.
- ``apagar_mensagens_vencidas`` (cron, 1 h): retenção da mensagem crua (padrão 90 dias) e
  dos fatos da ficha (``retencao_fatos_dias``, padrão 365).
- ``analisar_aprendizado_empresa`` e ``analisar_aprendizado_periodico`` (cron, 1 h): as
  sugestões de melhoria dos bots (padrão semanal por usuário).

Nenhum job envia mensagem por Slack ou WhatsApp.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select

from app.canais_empresa import clientes, conexoes, lgpd, resumo
from app.canais_empresa import conhecimento as base
from app.canais_empresa.tabelas import (
    AutorizacaoEmpresa,
    ConhecimentoEmpresa,
    ContatoEmpresa,
    MensagemEmpresa,
    PreferenciasCanaisEmpresa,
)

registro = logging.getLogger(__name__)

ESPERA_MINIMA = timedelta(minutes=2)
USUARIOS_POR_PASSADA = 20


async def _enriquecer_nomes_slack(fabrica: Any, usuario_id: UUID) -> None:
    """Confere o papel de todos os autores Slack pendentes antes de resumir.

    Nome conhecido ou lista manual não provam vínculo. Falha na consulta mantém o autor
    como cliente; convidados, externos e contas desativadas nunca ensinam a empresa.
    """
    async with fabrica() as sessao:
        pendentes = select(MensagemEmpresa.contato_id).where(
            MensagemEmpresa.usuario_id == usuario_id,
            MensagemEmpresa.processada_em.is_(None),
            MensagemEmpresa.texto.is_not(None),
        )
        contatos = list(
            await sessao.scalars(
                select(ContatoEmpresa).where(
                    ContatoEmpresa.usuario_id == usuario_id,
                    ContatoEmpresa.canal == "slack",
                    ContatoEmpresa.id.in_(pendentes),
                )
            )
        )
        if not contatos:
            return
        conexao = await conexoes.obter(sessao, usuario_id, "slack")
        for contato in contatos:
            contato.papel = "cliente"
        if conexao is not None:
            async with clientes.fabrica_http() or httpx.AsyncClient(
                timeout=15, trust_env=False
            ) as http:
                cliente = clientes.ClienteSlackLeitura(
                    conexoes.decifrar_segredos(conexao)["bot_token"], cliente=http
                )
                workspace = str(conexao.config.get("team_id") or "")
                for contato in contatos:
                    try:
                        nome, membro = await cliente.perfil_do_usuario(
                            contato.id_externo, workspace
                        )
                    except Exception:
                        registro.warning("não consegui conferir o vínculo no Slack")
                        continue
                    if nome:
                        contato.nome = nome
                    if membro:
                        contato.papel = "funcionario"
        await sessao.commit()


async def processar_canais_empresa(ctx: dict[str, Any], usuario_id: str) -> int:
    """Devolve quantas mensagens foram resumidas."""
    uid = UUID(usuario_id)
    await _enriquecer_nomes_slack(ctx["sessoes"], uid)
    resultado = await resumo.processar_usuario(ctx["sessoes"], ctx["redis_eventos"], uid)
    return resultado.mensagens


async def processar_pendentes_canais_empresa(ctx: dict[str, Any]) -> int:
    limite = datetime.now(UTC) - ESPERA_MINIMA
    async with ctx["sessoes"]() as sessao:
        usuarios = list(
            (
                await sessao.scalars(
                    select(MensagemEmpresa.usuario_id)
                    .where(
                        MensagemEmpresa.processada_em.is_(None),
                        MensagemEmpresa.texto.is_not(None),
                        MensagemEmpresa.recebida_em < limite,
                    )
                    .distinct()
                    .limit(USUARIOS_POR_PASSADA)
                )
            ).all()
        )
    total = 0
    for uid in usuarios:
        try:
            total += await processar_canais_empresa(ctx, str(uid))
        except Exception:
            registro.exception("falha ao resumir os canais do usuário %s", uid)
    return total


async def apagar_mensagens_vencidas(ctx: dict[str, Any]) -> int:
    async with ctx["sessoes"]() as sessao:
        apagadas = await lgpd.apagar_mensagens_vencidas(sessao)
        fatos = await lgpd.apagar_fatos_vencidos(sessao)
        await sessao.commit()
    if fatos:
        registro.info("retenção: %d fatos de ficha vencidos apagados", fatos)
    return apagadas


async def analisar_aprendizado_empresa(ctx: dict[str, Any], usuario_id: str) -> int:
    from app.canais_empresa.sugestoes import gerar_sugestoes

    return await gerar_sugestoes(ctx["sessoes"], ctx["redis_eventos"], UUID(usuario_id))


async def usuarios_para_analisar(sessao: Any, agora: datetime | None = None) -> list[UUID]:
    """Quem tem bot autorizado a ver o conhecimento, o intervalo venceu (0 = desligado) e a base
    mudou desde a última análise."""
    agora = agora or datetime.now(UTC)
    candidatos = (
        await sessao.scalars(
            select(AutorizacaoEmpresa.usuario_id)
            .where(AutorizacaoEmpresa.escopo == "conhecimento")
            .distinct()
        )
    ).all()
    devidos: list[UUID] = []
    for uid in candidatos:
        prefs = await sessao.get(PreferenciasCanaisEmpresa, uid)
        intervalo = prefs.sugestoes_intervalo_dias if prefs else 7
        ultima = prefs.ultima_analise_em if prefs else None
        if intervalo <= 0 or (ultima and ultima > agora - timedelta(days=intervalo)):
            continue
        mudou = await sessao.scalar(
            select(ConhecimentoEmpresa.id)
            .where(
                ConhecimentoEmpresa.usuario_id == uid,
                *base.condicoes_do_prompt(),  # só o que o usuário aprovou conta como mudança
                *([ConhecimentoEmpresa.atualizado_em > ultima] if ultima else []),
            )
            .limit(1)
        )
        if mudou is not None:
            devidos.append(uid)
    return devidos


async def analisar_aprendizado_periodico(ctx: dict[str, Any]) -> int:
    async with ctx["sessoes"]() as sessao:
        devidos = await usuarios_para_analisar(sessao)
    total = 0
    for uid in devidos[:USUARIOS_POR_PASSADA]:
        try:
            total += await analisar_aprendizado_empresa(ctx, str(uid))
        except Exception:
            registro.exception("falha ao analisar o aprendizado do usuário %s", uid)
    return total
