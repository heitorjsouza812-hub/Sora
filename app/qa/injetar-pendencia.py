"""Injeta, no backend REAL de QA, uma pergunta ou um pedido de aprovação numa conversa existente.

O modelo falso nunca pergunta nem pede aprovação, então o e2e não tem como provocar esses estados pela
cadeia. Este script grava a linha em `perguntas`/`aprovacoes` e publica o evento exatamente como o motor
faria (app.eventos.streams.publicar_evento); a resposta do usuário passa pelas rotas reais
(/v1/perguntas/{id}/responder e /v1/aprovacoes/{id}/decidir). O que NÃO cobre: a retomada da cadeia
(precisa de um modelo que chame `perguntar`/`criar_agente`).

Uso (na pasta backend, com o mesmo ambiente da API):
  uv run python ../app/qa/injetar-pendencia.py pergunta <conversa_id> [--orcamento]
  uv run python ../app/qa/injetar-pendencia.py aprovacao <conversa_id>
  uv run python ../app/qa/injetar-pendencia.py estado <id>      # imprime resposta/status gravados
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from redis.asyncio import Redis  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.banco import fabrica_sessoes  # noqa: E402
from app.core.config import obter_configuracao  # noqa: E402
from app.eventos.tipos import AprovacaoPedida, OpcaoPergunta, PerguntaEvento  # noqa: E402
from app.eventos.streams import publicar_evento  # noqa: E402
from app.modelos.tabelas import Aprovacao, Cadeia, Conversa, Pergunta  # noqa: E402


async def principal() -> None:
    modo, ident = sys.argv[1], UUID(sys.argv[2])
    fabrica = fabrica_sessoes()
    redis = Redis.from_url(obter_configuracao().redis_url, decode_responses=True)
    async with fabrica() as sessao:
        if modo == "estado":
            p = await sessao.get(Pergunta, ident)
            if p is not None:
                print(f"pergunta resposta={p.resposta!r} respondida={p.respondida_em is not None}")
                return
            a = await sessao.get(Aprovacao, ident)
            print(f"aprovacao status={a.status.value if a else None}")
            return
        conversa = await sessao.scalar(select(Conversa).where(Conversa.id == ident))
        assert conversa is not None, "conversa não encontrada"
        # Conversa com cadeia: a pergunta leva o cadeia_id e, sem etapa esperando, a rota só grava a resposta
        # (nenhum job). Em conversa sem cadeia a rota enfileira `retomar_conversa` e o modelo falso, que
        # sempre chama `falar`, entraria em laço.
        cadeia_id = await sessao.scalar(
            select(Cadeia.id).where(Cadeia.conversa_id == conversa.id).order_by(Cadeia.criada_em.desc()).limit(1)
        )
        if modo == "pergunta":
            orcamento = "--orcamento" in sys.argv
            texto = (
                "O orçamento deste pedido acabou. Quer continuar mesmo assim?"
                if orcamento
                else "Para quem é a campanha: clientes novos ou clientes de sempre?"
            )
            opcoes = (
                [("Continuar", "continuar"), ("Parar", "parar")]
                if orcamento
                else [("Clientes novos", "novos"), ("Clientes de sempre", "sempre")]
            )
            pergunta = Pergunta(
                id=uuid4(), conversa_id=conversa.id, cadeia_id=cadeia_id, texto=texto,
                opcoes=[{"rotulo": r, "valor": v} for r, v in opcoes], resposta_livre=not orcamento,
            )
            sessao.add(pergunta)
            await sessao.commit()
            await publicar_evento(
                redis,
                PerguntaEvento(
                    pergunta_id=pergunta.id, texto=texto,
                    opcoes=[OpcaoPergunta(rotulo=r, valor=v) for r, v in opcoes], resposta_livre=not orcamento,
                ),
                conversa.id, conversa.usuario_id,
            )
            print(pergunta.id)
        elif modo == "aprovacao":
            aprovacao = Aprovacao(
                id=uuid4(), usuario_id=conversa.usuario_id, etapa_id=None, agente_id=conversa.agente_id,
                acao={"ferramenta": "criar_agente", "nome": "Íris", "papel": "Organizar pesquisas"},  # sem conversa_id: a rota só grava
                avaliacao={"nivel": "medio"}, expira_em=datetime.now(UTC) + timedelta(minutes=10),
            )
            sessao.add(aprovacao)
            await sessao.commit()
            await publicar_evento(
                redis,
                AprovacaoPedida(
                    aprovacao_id=aprovacao.id, resumo="Criar o agente Íris (Organizar pesquisas)",
                    dano="O agente novo passa a poder usar ferramentas em seu nome.", quem_recebe=None,
                    expira_em=aprovacao.expira_em,
                ),
                conversa.id, conversa.usuario_id,
            )
            print(aprovacao.id)
    await redis.aclose()


asyncio.run(principal())
