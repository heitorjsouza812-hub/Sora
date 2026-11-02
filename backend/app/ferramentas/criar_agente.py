"""Ferramenta ``criar_agente`` (especificação §4): a Sora propõe um agente
individual. Sempre pede aprovação por cartão fixo (sem modelo revisor), com a
interrupção do LangGraph (§6.1). Respeita o limite de 5 agentes individuais.

Ao retomar, a função roda de novo desde o início; por isso o cartão pendente do mesmo
nome é reaproveitado e o agente só nasce uma vez (a decisão volta como
``DecisaoAprovacao``; qualquer valor que não seja ``negar`` conta como aprovado).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from langgraph.types import interrupt
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.agentes.aparencia import escolher_cor, movimento_do_individual
from app.core.banco import fabrica_sessoes
from app.eventos.tipos import AgenteCriado, AprovacaoPedida
from app.ferramentas.ambiente import emitir
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.modelos.enumeracoes import DecisaoAprovacao, StatusAprovacao, TipoAgente
from app.modelos.tabelas import Agente, Aprovacao

LIMITE_AGENTES_INDIVIDUAIS = 5
VALIDADE_DO_CARTAO = timedelta(minutes=10)


class CriarAgente(BaseModel):
    """Propõe criar um agente individual; o usuário aprova no cartão."""

    nome: str = Field(min_length=1, max_length=40)
    papel: str = Field(min_length=1)


def resumo_do_cartao(nome: str, papel: str) -> str:
    return f"A Sora quer criar o agente {nome}: {papel}"


async def criar_agente(args: CriarAgente, contexto: ContextoFerramenta) -> str:
    """Cria o cartão de aprovação, interrompe e, se aprovado, cria o agente."""
    nome = args.nome.strip()
    acao = {"ferramenta": "criar_agente", "nome": nome, "papel": args.papel}
    novo_cartao = None
    async with fabrica_sessoes()() as sessao:
        ativos = list(
            await sessao.scalars(
                select(Agente).where(
                    Agente.usuario_id == contexto.usuario_id,
                    Agente.tipo == TipoAgente.INDIVIDUAL,
                    Agente.apagado_em.is_(None),
                )
            )
        )
        if any(a.nome.casefold() == nome.casefold() and a.papel == args.papel for a in ativos):
            return f"O agente {nome} já existe."
        if len(ativos) >= LIMITE_AGENTES_INDIVIDUAIS:
            raise ErroFerramenta(
                f"Limite de {LIMITE_AGENTES_INDIVIDUAIS} agentes individuais atingido. "
                "Peça ao usuário para apagar um antes."
            )
        cartao = await sessao.scalar(
            select(Aprovacao)
            .where(
                Aprovacao.usuario_id == contexto.usuario_id,
                Aprovacao.agente_id == contexto.agente_id,
                Aprovacao.etapa_id == contexto.etapa_id,
                Aprovacao.acao == acao,
            )
            .limit(1)
        )
        if cartao is None:
            cartao = Aprovacao(
                usuario_id=contexto.usuario_id,
                etapa_id=contexto.etapa_id,
                agente_id=contexto.agente_id,
                acao=acao,
                avaliacao={"modelo_revisor": False, "dano": "baixo"},
                status=StatusAprovacao.PENDENTE,
                expira_em=datetime.now(UTC) + VALIDADE_DO_CARTAO,
            )
            sessao.add(cartao)
            await sessao.commit()
            novo_cartao = AprovacaoPedida(
                aprovacao_id=cartao.id,
                resumo=resumo_do_cartao(nome, args.papel),
                dano="Cria um agente novo na sua conta.",
                quem_recebe=None,
                expira_em=cartao.expira_em,
            )
        aprovacao_id = cartao.id
        status_do_cartao = cartao.status
    if novo_cartao is not None:
        await emitir(contexto, novo_cartao)

    if status_do_cartao == StatusAprovacao.PENDENTE:
        decisao = interrupt({"tipo": "aprovacao", "aprovacao_id": str(aprovacao_id)})
    elif status_do_cartao == StatusAprovacao.PERMITIDA:
        decisao = DecisaoAprovacao.PERMITIR_UMA_VEZ
    else:
        decisao = DecisaoAprovacao.NEGAR
    if str(decisao) in (DecisaoAprovacao.NEGAR.value, StatusAprovacao.NEGADA.value, "expirada"):
        return "O usuário não aprovou a criação do agente."

    async with fabrica_sessoes()() as sessao:
        ja = await sessao.scalar(
            select(func.count())
            .select_from(Agente)
            .where(
                Agente.usuario_id == contexto.usuario_id,
                Agente.tipo == TipoAgente.INDIVIDUAL,
                Agente.nome == nome,
                Agente.papel == args.papel,
                Agente.apagado_em.is_(None),
            )
        )
        if ja:
            return f"O agente {nome} foi criado."
        cores = {
            c
            for c in await sessao.scalars(
                select(Agente.cor).where(
                    Agente.usuario_id == contexto.usuario_id, Agente.apagado_em.is_(None)
                )
            )
        }
        agente = Agente(
            usuario_id=contexto.usuario_id,
            tipo=TipoAgente.INDIVIDUAL,
            nome=nome,
            funcao=args.papel,
            papel=args.papel,
            cor=escolher_cor(cores),
            movimento=movimento_do_individual(args.papel),
        )
        sessao.add(agente)
        await sessao.commit()
        evento = AgenteCriado(
            agente_id=agente.id,
            tipo=agente.tipo,
            nome=agente.nome,
            funcao=agente.funcao,
            cor=agente.cor,
            movimento=agente.movimento,
        )
    await emitir(contexto, evento)
    return f"Agente {nome} criado."
