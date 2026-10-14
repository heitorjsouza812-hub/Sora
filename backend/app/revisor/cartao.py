"""Cartão fixo de aprovação do ``criar_agente`` (fase 1, sem modelo revisor).

Especificação: §4 (``criar_agente(nome, papel)``: "sempre pede aprovação por cartão fixo (sem
modelo revisor)") e §6.1 (usa a interrupção do LangGraph: a etapa vai para
``aguardando_aprovacao`` e o job termina; ao decidir, ``Command(resume=decisão)``).

Este módulo monta o cartão e grava/consulta a aprovação. Quem pausa e retoma a etapa é a
ferramenta em ``app/ferramentas/`` e o job ``executar_etapa``. O limite de 5 agentes individuais
é checado antes, na ferramenta (a API devolve 409).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.modelos.enumeracoes import DecisaoAprovacao
from app.revisor.esquemas import CartaoAprovacao

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def resumo_do_cartao(nome: str, papel: str) -> str:
    """Texto do cartão, ex.: "A Sora quer criar o agente <nome>: <papel>"."""
    raise NotImplementedError


async def criar_cartao_criar_agente(
    sessao: AsyncSession,
    usuario_id: UUID,
    agente_id: UUID,
    etapa_id: UUID | None,
    nome: str,
    papel: str,
) -> CartaoAprovacao:
    """Grava a linha em ``aprovacoes`` (``acao`` = criar_agente, ``expira_em`` = agora + 10 min)
    e devolve o cartão para o evento ``aprovacao.pedida``."""
    raise NotImplementedError


async def decidir_aprovacao(
    sessao: AsyncSession,
    usuario_id: UUID,
    aprovacao_id: UUID,
    decisao: DecisaoAprovacao,
) -> None:
    """Registra a decisão do usuário. ``sempre_permitir`` cria uma ``regras_permissao`` (o
    agente_id da regra é o do cartão)."""
    raise NotImplementedError


async def marcar_aprovacao_expirada(sessao: AsyncSession, aprovacao_id: UUID) -> bool:
    """Passa a aprovação de ``pendente`` para ``expirada``. Devolve False se já estava decidida.

    Só o helper de banco: o job agendado para ``expira_em`` é ``workers/aprovacoes.py``
    (``expirar_aprovacao``), que chama esta função, emite ``aprovacao.resolvida`` e retoma a
    etapa com "negado".
    """
    raise NotImplementedError
