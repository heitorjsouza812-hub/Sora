"""Job ``compactar_historico`` (Âncora, etapa 4): o botão "Compactar agora" e a compactação
pedida fora do turno.

Compactar dentro de um turno é o ``MiddlewareContexto``; aqui o mesmo plano
(``app/contexto/compactador.py``) age sobre o estado salvo da conversa no checkpointer, para
quando o agente está parado.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any
from uuid import UUID

from app.contexto import SituacaoCompactacao, medir
from app.contexto.compactador import atualizacao_do_estado, planejar, tokens_do_historico
from app.contexto.estado import ler, registrar_e_publicar
from app.contexto.porta import PortaContexto, janela_do_modelo
from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import Agente, Conversa

registro = logging.getLogger(__name__)


async def compactar_historico(
    ctx: dict[str, Any], conversa_id: str, agente_id: str, fio: str = "principal"
) -> str:
    """Resume o começo do histórico da conversa. Devolve ``compactado``, ``nada`` ou ``falhou``."""
    from app.agentes import ContextoAgente, montar_agente
    from app.agentes.checkpointer import thread_da_conversa
    from app.orquestrador.modelos import modelos_do_papel

    redis = ctx["redis_eventos"]
    async with ctx["sessoes"]() as sessao:
        conversa = await sessao.get(Conversa, UUID(conversa_id))
        agente = await sessao.get(Agente, UUID(agente_id))
        if conversa is None or agente is None or conversa.agente_id != agente.id:
            return "nada"
        papel = "sora" if agente.tipo == TipoAgente.SORA else "individual"
        modelos = await modelos_do_papel(sessao, conversa.usuario_id, papel, dificuldade=1)
        usuario_id = conversa.usuario_id
    porta = PortaContexto(
        redis=redis,
        usuario_id=usuario_id,
        conversa_id=UUID(conversa_id),
        agente_id=agente.id,
        fio=fio,
    )
    contexto = ContextoAgente(
        usuario_id=usuario_id, agente_id=agente.id, conversa_id=UUID(conversa_id), papel=papel
    )
    grafo = await montar_agente(contexto, modelos, ctx["checkpointer"])
    config = {"configurable": {"thread_id": thread_da_conversa(UUID(conversa_id))}}
    estado_atual = await ler(redis, agente.id, fio)
    try:
        instantaneo = await grafo.aget_state(config)
        mensagens = list((instantaneo.values or {}).get("messages", []))
        janela = (estado_atual.janela if estado_atual else None) or janela_do_modelo(None)
        antes = medir(
            agente.id, fio, janela=janela, tokens_informados=tokens_do_historico(mensagens)
        )
        plano = await planejar(mensagens, antes.janela, porta.resumir)
        if plano is None:
            await registrar_e_publicar(
                redis,
                replace(antes, compactacao=SituacaoCompactacao.PARADA),
                usuario_id=usuario_id,
                conversa_id=UUID(conversa_id),
                fim_da_compactacao=True,
            )
            return "nada"
        await grafo.aupdate_state(config, {"messages": atualizacao_do_estado(plano)})
        depois = medir(agente.id, fio, janela=antes.janela, tokens_informados=plano.tokens_depois)
        await registrar_e_publicar(
            redis, depois, usuario_id=usuario_id, conversa_id=UUID(conversa_id),
            fim_da_compactacao=True,
        )  # fmt: skip
        return "compactado"
    except Exception:
        registro.exception("compactar_historico falhou (conversa %s)", conversa_id)
        base = estado_atual or medir(agente.id, fio, janela=None, tokens_informados=0)
        await registrar_e_publicar(
            redis,
            replace(base, compactacao=SituacaoCompactacao.FALHOU),
            usuario_id=usuario_id,
            conversa_id=UUID(conversa_id),
            fim_da_compactacao=True,
        )
        return "falhou"
