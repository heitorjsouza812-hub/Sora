"""Tipos do revisor: avaliação do modelo, cartão de aprovação e decisão do usuário.

Campos e ordem vêm do prompt "Revisor de ações" (``03-prompts.md``) e da API
``POST /v1/aprovacoes/{id}/decidir`` (§2). O evento ``aprovacao.pedida`` leva
``aprovacao_id, resumo, dano, quem_recebe, expira_em``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

# Cartões de tarefas em segundo plano expiram em 10 minutos (plano 01, §6).
APROVACAO_EXPIRA_MINUTOS = 10


class Dano(StrEnum):
    NENHUM = "nenhum"
    EFEITO_EXTERNO = "efeito_externo"
    VAZAMENTO = "vazamento"
    PERDA_DE_DADOS = "perda_de_dados"
    COMPROMETER_MAQUINA = "comprometer_maquina"
    REGRA_DO_USUARIO = "regra_do_usuario"


class Destino(StrEnum):
    NAO_EXTERNO = "nao_externo"
    CONFIAVEL = "confiavel"
    NAO_AUTORIZADO = "nao_autorizado"


class DecisaoRevisor(StrEnum):
    PERMITIR = "PERMITIR"
    BLOQUEAR = "BLOQUEAR"


class AvaliacaoRevisor(BaseModel):
    """Saída do revisor de ações (vai em ``aprovacoes.avaliacao``). Ordem dos campos importa."""

    dano: Dano
    quem_recebe: str | None = None
    destino: Destino
    decisao: DecisaoRevisor
    motivo: str


class AcaoProposta(BaseModel):
    """Vai em ``aprovacoes.acao``: ``{"ferramenta": "...", "argumentos": {...}}``."""

    ferramenta: str
    argumentos: dict[str, Any]


class CartaoAprovacao(BaseModel):
    """O que o app mostra: Permitir uma vez · Sempre permitir · Negar."""

    aprovacao_id: UUID
    agente_id: UUID
    etapa_id: UUID | None = None
    resumo: str
    dano: Dano
    quem_recebe: str | None = None
    expira_em: datetime
    acao: AcaoProposta
