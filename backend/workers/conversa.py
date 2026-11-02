"""Job de resposta direta (especificação §2, "O que acontece num POST
/mensagens", passos 3 e 5; §6, ``responder_direto``).

Resposta no modo ``direto`` (N1 ou N2) ou num agente individual: o agente roda com as
ferramentas reais e fala pela ferramenta ``falar`` (que grava a mensagem e emite
``mensagem.inicio/delta/fim``). Se o modelo respondeu em texto puro, sem chamar ``falar``, o
worker fala por ele. Termina com ``sugestoes``.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import func, select

from app.eventos.streams import publicar_evento
from app.eventos.tipos import SugestoesEvento
from app.llm.falso import criar_modelo_falso, modelo_falso_ativo
from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import Agente, Conversa, Mensagem

registro = logging.getLogger(__name__)


def _texto_da_resposta(resultado: dict[str, Any]) -> str:
    for mensagem in reversed(resultado.get("messages", [])):
        if isinstance(mensagem, AIMessage) and isinstance(mensagem.content, str):
            if mensagem.content.strip():
                return mensagem.content.strip()
    return ""


async def responder_direto(ctx: dict[str, Any], mensagem_id: str) -> None:
    """Roda a Sora (ou o agente individual) e manda o texto pelos eventos
    ``mensagem.*``, terminando com ``sugestoes``. Quem põe na fila: a API."""
    from app.agentes import ContextoAgente
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.falar import Falar, falar
    from app.orquestrador.modelos import modelos_do_papel
    from workers.cadeia import dependencias_da_etapa

    async with ctx["sessoes"]() as sessao:
        mensagem = await sessao.get(Mensagem, UUID(mensagem_id))
        if mensagem is None:
            return
        conversa = await sessao.get(Conversa, mensagem.conversa_id)
        agente = await sessao.get(Agente, conversa.agente_id) if conversa else None
        if conversa is None or agente is None:
            return
        papel = "sora" if agente.tipo == TipoAgente.SORA else "individual"
        modelos = await modelos_do_papel(
            sessao,
            conversa.usuario_id,
            papel,
            dificuldade=1,
            conversa_privada=conversa.privada,
        )
        usuario_id, conversa_id, agente_id = conversa.usuario_id, conversa.id, agente.id
        texto = mensagem.conteudo
        antes = await sessao.scalar(
            select(func.count()).select_from(Mensagem).where(Mensagem.conversa_id == conversa_id)
        )

    contexto = ContextoAgente(
        usuario_id=usuario_id,
        agente_id=agente_id,
        conversa_id=conversa_id,
        papel=papel,
        dependencias=dependencias_da_etapa(ctx, usuario_id=usuario_id, conversa_id=conversa_id),
    )
    if modelo_falso_ativo():
        # O roteiro da Sora falsa chama ``falar`` em ciclo para servir outros fluxos do agente.
        # Na resposta direta basta uma resposta textual, enviada pela ferramenta real.
        resposta_falsa = await criar_modelo_falso("resposta_direta").ainvoke([HumanMessage(texto)])
        await falar(
            Falar(texto=str(resposta_falsa.content)),
            ContextoFerramenta(usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id),
        )
        await publicar_evento(
            ctx["redis_eventos"], SugestoesEvento(itens=[]), conversa_id, usuario_id
        )
        return
    await _rodar_e_falar(
        ctx, contexto, modelos, antes=antes, entrada={"messages": [HumanMessage(texto)]}
    )


MENSAGEM_FALHA = (
    "Não consegui terminar essa resposta agora (o modelo de IA não respondeu). "
    "Tente de novo em instantes ou confira o provedor em Configurações → Modelos de IA."
)


async def _rodar_e_falar(
    ctx: dict[str, Any],
    contexto: Any,
    modelos: list[Any],
    *,
    antes: int | None,
    entrada: dict[str, Any] | None = None,
    resposta: Any | None = None,
) -> None:
    """Roda (ou retoma) o agente da conversa. Se o modelo respondeu em texto puro, o worker
    fala por ele; se o provedor falhar, a conversa recebe um aviso em PT-BR em vez de ficar muda."""
    from app.agentes import montar_e_rodar_agente
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.falar import Falar, falar

    ferramenta = ContextoFerramenta(
        usuario_id=contexto.usuario_id,
        agente_id=contexto.agente_id,
        conversa_id=contexto.conversa_id,
    )
    try:
        resultado = await montar_e_rodar_agente(
            contexto=contexto,
            modelos=modelos,
            checkpointer=ctx["checkpointer"],
            entrada=entrada,
            resposta=resposta,
        )
    except Exception:
        registro.exception("o agente da conversa %s falhou", contexto.conversa_id)
        await falar(Falar(texto=MENSAGEM_FALHA), ferramenta)
        await publicar_evento(
            ctx["redis_eventos"],
            SugestoesEvento(itens=[]),
            contexto.conversa_id,
            contexto.usuario_id,
        )
        return

    if not resultado.get("__interrupt__"):
        async with ctx["sessoes"]() as sessao:
            depois = await sessao.scalar(
                select(func.count())
                .select_from(Mensagem)
                .where(Mensagem.conversa_id == contexto.conversa_id)
            )
        texto = _texto_da_resposta(resultado)
        if (antes is None or depois == antes) and texto:
            # O modelo respondeu em texto puro: o worker fala por ele.
            await falar(Falar(texto=texto), ferramenta)
    await publicar_evento(
        ctx["redis_eventos"], SugestoesEvento(itens=[]), contexto.conversa_id, contexto.usuario_id
    )


async def retomar_conversa(ctx: dict[str, Any], conversa_id: str, resposta: Any) -> None:
    """Retoma o agente de uma conversa fora de cadeia (Sora ou agente individual) depois que o
    usuário respondeu uma pergunta ou decidiu uma aprovação. Quem põe na fila: a API."""
    from app.agentes import ContextoAgente
    from app.orquestrador.modelos import modelos_do_papel
    from workers.cadeia import dependencias_da_etapa, valor_da_retomada

    valor = valor_da_retomada(resposta)
    if valor is None:
        return
    async with ctx["sessoes"]() as sessao:
        conversa = await sessao.get(Conversa, UUID(conversa_id))
        agente = await sessao.get(Agente, conversa.agente_id) if conversa else None
        if conversa is None or agente is None:
            return
        papel = "sora" if agente.tipo == TipoAgente.SORA else "individual"
        modelos = await modelos_do_papel(
            sessao, conversa.usuario_id, papel, dificuldade=1, conversa_privada=conversa.privada
        )
        usuario_id, agente_id = conversa.usuario_id, agente.id
    contexto = ContextoAgente(
        usuario_id=usuario_id,
        agente_id=agente_id,
        conversa_id=UUID(conversa_id),
        papel=papel,
        dependencias=dependencias_da_etapa(
            ctx, usuario_id=usuario_id, conversa_id=UUID(conversa_id)
        ),
    )
    await _rodar_e_falar(ctx, contexto, modelos, antes=None, resposta=valor)
