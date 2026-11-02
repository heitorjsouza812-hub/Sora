"""Job ``responder_canal`` (Relógio, etapa 4): mensagem que chegou por um aplicativo de mensagens
(hoje o Telegram) vira mensagem na conversa "Telegram" da Sora do usuário, a Sora responde como
em qualquer chat (o app também mostra) e a resposta volta pelo canal.

Só resposta direta: o pedido grande (cadeia de agentes) fica para o app. O canal só liga com
``TELEGRAM_TOKEN_BOT`` e ``TELEGRAM_SEGREDO_WEBHOOK``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage
from sqlalchemy import select

from app.canais import INSTRUCAO_CANAL
from app.canais.telegram import ClienteTelegram, ErroTelegram
from app.core.config import obter_configuracao
from app.eventos.streams import publicar_evento
from app.eventos.tipos import SugestoesEvento
from app.llm.falso import criar_modelo_falso, modelo_falso_ativo
from app.modelos.enumeracoes import AutorMensagem, TipoAgente, TipoConversa
from app.modelos.tabelas import Agente, Conversa, Mensagem

registro = logging.getLogger(__name__)

TITULO_CONVERSA = "Telegram"
TEXTO_FALHA = "Não consegui responder agora. Tente de novo em instantes ou abra o app da Sora."


async def _conversa_do_canal(sessao: Any, usuario_id: UUID) -> tuple[Conversa, Agente] | None:
    sora = await sessao.scalar(
        select(Agente).where(
            Agente.usuario_id == usuario_id,
            Agente.tipo == TipoAgente.SORA,
            Agente.apagado_em.is_(None),
        )
    )
    if sora is None:
        return None
    conversa = await sessao.scalar(
        select(Conversa)
        .where(
            Conversa.usuario_id == usuario_id,
            Conversa.agente_id == sora.id,
            Conversa.titulo == TITULO_CONVERSA,
        )
        .order_by(Conversa.criada_em)
        .limit(1)
    )
    if conversa is None:
        conversa = Conversa(
            usuario_id=usuario_id,
            agente_id=sora.id,
            tipo=TipoConversa.CHAT,
            titulo=TITULO_CONVERSA,
        )
        sessao.add(conversa)
        await sessao.flush()
    return conversa, sora


async def responder_canal(
    ctx: dict[str, Any], usuario_id: str, canal: str, chat_id: str, texto: str
) -> int:
    """Devolve quantas mensagens saíram para o canal."""
    config = obter_configuracao()
    if canal != "telegram" or config.telegram_token_bot is None:
        return 0
    from app.agentes import ContextoAgente
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.falar import Falar, falar
    from app.orquestrador.modelos import modelos_do_papel
    from workers.cadeia import dependencias_da_etapa
    from workers.conversa import _rodar_e_falar

    uid = UUID(usuario_id)
    cliente = ClienteTelegram(config.telegram_token_bot.get_secret_value())
    inicio = datetime.now(UTC)
    async with ctx["sessoes"]() as sessao:
        achado = await _conversa_do_canal(sessao, uid)
        if achado is None:
            return 0
        conversa, sora = achado
        conversa_id, agente_id = conversa.id, sora.id
        sessao.add(
            Mensagem(
                conversa_id=conversa_id,
                autor=AutorMensagem.USUARIO,
                conteudo=texto,
                visivel=True,
                criada_em=inicio,
            )
        )
        modelos = (
            [criar_modelo_falso("resposta_direta")]
            if modelo_falso_ativo()
            else await modelos_do_papel(sessao, uid, "sora", dificuldade=1)
        )
        await sessao.commit()

    ferramenta = ContextoFerramenta(usuario_id=uid, agente_id=agente_id, conversa_id=conversa_id)
    try:
        if modelo_falso_ativo():
            resposta = await modelos[0].ainvoke([HumanMessage(texto)])
            await falar(Falar(texto=str(resposta.content)), ferramenta)
            await publicar_evento(ctx["redis_eventos"], SugestoesEvento(itens=[]), conversa_id, uid)
        else:
            contexto = ContextoAgente(
                usuario_id=uid,
                agente_id=agente_id,
                conversa_id=conversa_id,
                papel="sora",
                dependencias=dependencias_da_etapa(ctx, usuario_id=uid, conversa_id=conversa_id),
            )
            await _rodar_e_falar(
                ctx,
                contexto,
                modelos,
                antes=None,
                entrada={"messages": [HumanMessage(f"{INSTRUCAO_CANAL}\n\n{texto}")]},
            )
    except Exception:
        registro.exception("a resposta do canal %s falhou", canal)
    async with ctx["sessoes"]() as sessao:
        respostas = list(
            (
                await sessao.scalars(
                    select(Mensagem.conteudo)
                    .where(
                        Mensagem.conversa_id == conversa_id,
                        Mensagem.autor != AutorMensagem.USUARIO,
                        Mensagem.visivel.is_(True),
                        Mensagem.criada_em > inicio,
                    )
                    .order_by(Mensagem.criada_em)
                )
            ).all()
        )
    enviadas = 0
    try:
        for resposta_texto in respostas or [TEXTO_FALHA]:
            enviadas += await cliente.enviar(chat_id, resposta_texto)
    except ErroTelegram:
        registro.warning("não consegui entregar a resposta no Telegram", exc_info=True)
    return enviadas
