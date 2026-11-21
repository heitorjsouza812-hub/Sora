"""Job ``aprender_com_correcoes`` (Onda 3, item 15): relê o trecho novo de uma conversa e guarda
as correções e preferências do usuário como memória. Regras em ``app/memoria/aprendizado.py``."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.llm.falso import modelo_falso_ativo
from app.modelos.tabelas import Agente, Conversa, Usuario

registro = logging.getLogger(__name__)

PRAZO_S = 60


async def _servico_memoria(sessao: Any, usuario_id: UUID) -> Any:
    from app.memoria.servico import ArmazemMemoriasSQL, ServicoMemoria
    from app.memoria.vetorizador import vetorizador_do_usuario

    return ServicoMemoria(
        ArmazemMemoriasSQL(sessao), await vetorizador_do_usuario(sessao, usuario_id)
    )


async def aprender_com_correcoes(ctx: dict[str, Any], conversa_id: str) -> int:
    """Devolve quantas memórias novas guardou. Nunca levanta (falha fica no log)."""
    from app.memoria import aprendizado as ap

    async with ctx["sessoes"]() as sessao:
        conversa = await sessao.get(Conversa, UUID(conversa_id), with_for_update=True)
        if conversa is None or conversa.privada:
            return 0
        usuario = await sessao.get(Usuario, conversa.usuario_id)
        if usuario is None or not usuario.aprender_a_cada:
            return 0
        novas = await ap.mensagens_novas_do_usuario(sessao, conversa.id, conversa.aprendizado_ate)
        if novas < usuario.aprender_a_cada:
            return 0  # outro worker já releu este trecho
        trecho, ultima = await ap.trecho_para_reler(sessao, conversa)
        if ultima is not None:
            # A marca anda antes do modelo: falha (limite da conta) não relê o mesmo trecho.
            conversa.aprendizado_ate = ultima
        usuario_id, agente_id = conversa.usuario_id, conversa.agente_id
        agente = await sessao.get(Agente, agente_id)
        nome_do_bot = agente.nome if agente is not None else "Sora"
        servico = await _servico_memoria(sessao, usuario_id)
        existentes = [r.conteudo for r in await servico.armazem.listar(usuario_id, agente_id)]
        await sessao.commit()
    if not any(linha.autor == "usuario" for linha in trecho):
        return 0

    if modelo_falso_ativo():
        bruto: Any = ap.propostas_do_modelo_falso(trecho)
    else:
        try:
            from app.llm.estruturada import com_saida_estruturada, instrucoes_json
            from app.memoria.aprendizado import PropostasMemoria
            from app.orquestrador.modelos import modelos_do_papel

            async with ctx["sessoes"]() as sessao:
                modelos = await modelos_do_papel(
                    sessao, usuario_id, "memoria_sintese", dificuldade=1, precisa=()
                )
            modelo = com_saida_estruturada(modelos[0], PropostasMemoria)
            resposta = await asyncio.wait_for(
                modelo.ainvoke(
                    [
                        SystemMessage(instrucoes_json(PropostasMemoria)),
                        HumanMessage(ap.montar_prompt(nome_do_bot, trecho, existentes)),
                    ]
                ),
                PRAZO_S,
            )
            bruto = (
                resposta.model_dump(mode="json") if isinstance(resposta, BaseModel) else resposta
            )
        except Exception:
            registro.warning(
                "não consegui reler a conversa %s para aprender", conversa_id, exc_info=True
            )
            return 0

    guardadas = 0
    for aprendida in ap.conferir_propostas(bruto, trecho, existentes):
        escopo = None if aprendida.geral else agente_id
        try:
            async with ctx["sessoes"]() as sessao:
                servico = await _servico_memoria(sessao, usuario_id)
                antes = {r.id for r in await servico.armazem.listar(usuario_id, escopo)}
                memoria = await servico.lembrar(
                    usuario_id, escopo, aprendida.conteudo, explicita=False
                )
                await sessao.commit()
        except Exception:
            registro.warning("não consegui guardar uma memória aprendida", exc_info=True)
            continue
        if memoria.id in antes:
            continue
        guardadas += 1
        await _avisar(ctx, usuario_id, agente_id, UUID(conversa_id), memoria)
    return guardadas


async def _avisar(
    ctx: dict[str, Any], usuario_id: UUID, agente_id: UUID, conversa_id: UUID, memoria: Any
) -> None:
    """Chip "Guardei isto" (com Desfazer) na conversa. Falha do Redis não desfaz a memória."""
    from app.eventos.equipe import (
        MAX_TEXTO_MEMORIA_EVENTO,
        MemoriaCriadaEvento,
        publicar_evento_equipe,
    )

    texto = memoria.conteudo
    if len(texto) > MAX_TEXTO_MEMORIA_EVENTO:
        texto = texto[: MAX_TEXTO_MEMORIA_EVENTO - 1].rstrip() + "…"
    try:
        await publicar_evento_equipe(
            ctx["redis_eventos"],
            MemoriaCriadaEvento(
                memoria_id=memoria.id,
                agente_id=agente_id,
                conversa_id=conversa_id,
                texto=texto,
            ),
            usuario_id,
        )
    except Exception:
        registro.warning("não consegui avisar a memória aprendida", exc_info=True)
