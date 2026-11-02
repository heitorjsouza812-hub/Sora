"""Job de resposta direta (especificação §2, "O que acontece num POST
/mensagens", passos 3 e 5; §6, ``responder_direto``).

Resposta no modo ``direto`` (N1 ou N2) ou num agente individual: o agente roda com as
ferramentas reais e fala pela ferramenta ``falar`` (que grava a mensagem e emite
``mensagem.inicio/delta/fim``). Se o modelo respondeu em texto puro, sem chamar ``falar``, o
worker fala por ele. Termina com ``sugestoes``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import func, select

from app.eventos.streams import publicar_evento
from app.eventos.tipos import SugestoesEvento
from app.llm.falso import criar_modelo_falso, modelo_falso_ativo
from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import Agente, Conversa, Mensagem


def _texto_da_resposta(resultado: dict[str, Any]) -> str:
    for mensagem in reversed(resultado.get("messages", [])):
        if isinstance(mensagem, AIMessage) and isinstance(mensagem.content, str):
            if mensagem.content.strip():
                return mensagem.content.strip()
    return ""


async def responder_direto(ctx: dict[str, Any], mensagem_id: str) -> None:
    """Roda a Sora (ou o agente individual) e manda o texto pelos eventos
    ``mensagem.*``, terminando com ``sugestoes``. Quem põe na fila: a API."""
    from app.agentes import ContextoAgente, montar_e_rodar_agente
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
        dependencias=dependencias_da_etapa(),
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
    resultado = await montar_e_rodar_agente(
        contexto=contexto,
        modelos=modelos,
        checkpointer=ctx["checkpointer"],
        entrada={"messages": [HumanMessage(texto)]},
    )

    if not resultado.get("__interrupt__"):
        async with ctx["sessoes"]() as sessao:
            depois = await sessao.scalar(
                select(func.count())
                .select_from(Mensagem)
                .where(Mensagem.conversa_id == conversa_id)
            )
        resposta = _texto_da_resposta(resultado)
        if depois == antes and resposta:
            # O modelo respondeu em texto puro: o worker fala por ele.
            await falar(
                Falar(texto=resposta),
                ContextoFerramenta(
                    usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id
                ),
            )
    await publicar_evento(ctx["redis_eventos"], SugestoesEvento(itens=[]), conversa_id, usuario_id)
