"""Revisor de ações (FASE 3 — só esqueleto).

Especificação: plano 01 "Segurança e aprovações"; prompts 03 "Revisor de ações"; §5 (papel
``revisor``, modelo preferido ``groq/openai/gpt-oss-safeguard-20b``); §6.1 (na fase 3 usa o
``HumanInTheLoopMiddleware``); §8.5 (30 ações rotuladas, incluindo comandos disfarçados:
base64, nome trocado, divididos em partes; nenhuma ação externa ou destrutiva passa sem
aprovação).

Antes de chamar o modelo, o backend checa ``regras_permissao``: se uma regra "sempre permitir"
casar, a ação passa direto. Desligado pela flag ``revisor.acoes_ativo``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.revisor.esquemas import AcaoProposta, AvaliacaoRevisor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Nome do prompt no registro de ``app/agentes/prompts.py`` (VERSOES): arquivo
# ``prompts/revisor_acoes.v1.md``, carregado com ``carregar_prompt(PROMPT_REVISOR)``.
PROMPT_REVISOR = "revisor_acoes"

# Ferramentas que passam pelo revisor (§4, coluna "Revisor"). ``criar_agente`` NÃO está aqui:
# ela usa o cartão fixo de ``cartao.py``.
FERRAMENTAS_REVISADAS: frozenset[str] = frozenset({"chamar_conector", "executar_comando"})
PREFIXO_FERRAMENTAS_NAVEGADOR = "navegador_"


def exige_revisao(ferramenta: str) -> bool:
    """True para as ferramentas marcadas com "sim" na especificação."""
    raise NotImplementedError


async def regra_permite(
    sessao: AsyncSession, usuario_id: UUID, agente_id: UUID, acao: AcaoProposta
) -> bool:
    """True se uma ``regras_permissao`` "sempre permitir" casa com a ação."""
    raise NotImplementedError


async def revisar_acao(
    sessao: AsyncSession,
    usuario_id: UUID,
    agente_id: UUID,
    acao: AcaoProposta,
    pedidos_do_usuario: list[str],
) -> AvaliacaoRevisor:
    """Chama o modelo revisor (papel ``revisor``) e valida a saída. Qualquer erro ou JSON
    inválido é tratado como BLOQUEAR (falha fechada)."""
    raise NotImplementedError


async def registrar_acao(
    sessao: AsyncSession,
    usuario_id: UUID,
    agente_id: UUID,
    etapa_id: UUID | None,
    acao: AcaoProposta,
    resumo: str,
    aprovacao_id: UUID | None,
) -> None:
    """Grava em ``registro_acoes`` todo efeito externo (data, agente e motivo)."""
    raise NotImplementedError
