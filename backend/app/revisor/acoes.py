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
    """True para as ferramentas marcadas com "sim" na especificação.

    Também vale para ferramentas de conector (``mcp__…``) que não parecem só leitura; a
    tabela completa está em ``app/revisor/politica.py``.
    """
    from app.revisor.politica import Politica, politica_da_ferramenta

    if ferramenta in FERRAMENTAS_REVISADAS:
        return True
    return politica_da_ferramenta(ferramenta) is Politica.REVISOR


async def regra_permite(
    sessao: AsyncSession, usuario_id: UUID, agente_id: UUID, acao: AcaoProposta
) -> bool:
    """True se uma regra "sempre permitir" do usuário casa com a ação.

    Vale para o agente da regra (ou todos, se ``agente_id`` é nulo) e a mesma ferramenta. Uma
    ``condicao`` não vazia exige cada par chave/valor igual nos argumentos (condição ilegível =
    não casa). Ferramenta de cartão fixo nunca é liberada por regra.
    """
    from sqlalchemy import or_, select

    from app.modelos.tabelas import RegraPermissao
    from app.revisor.politica import Politica, politica_da_ferramenta

    if politica_da_ferramenta(acao.ferramenta) is Politica.CARTAO_FIXO:
        return False
    regras = (
        await sessao.scalars(
            select(RegraPermissao).where(
                RegraPermissao.usuario_id == usuario_id,
                RegraPermissao.ferramenta == acao.ferramenta,
                or_(RegraPermissao.agente_id.is_(None), RegraPermissao.agente_id == agente_id),
            )
        )
    ).all()
    for regra in regras:
        condicao = regra.condicao
        if isinstance(condicao, dict) and all(
            acao.argumentos.get(chave) == valor for chave, valor in condicao.items()
        ):
            return True
    return False


async def revisar_acao(
    sessao: AsyncSession,
    usuario_id: UUID,
    agente_id: UUID,
    acao: AcaoProposta,
    pedidos_do_usuario: list[str],
) -> AvaliacaoRevisor:
    """Chama o modelo revisor (papel ``revisor``) e valida a saída. Qualquer erro ou JSON
    inválido é tratado como BLOQUEAR (falha fechada).

    Quem roda o juiz no worker é ``app/revisor/execucao.py`` (``conferir_acao``); esta função é
    a decisão sem modelo: regra do usuário libera, o resto bloqueia.
    """
    from app.revisor.esquemas import Dano, DecisaoRevisor, Destino
    from app.revisor.juiz import bloqueio

    if await regra_permite(sessao, usuario_id, agente_id, acao):
        return AvaliacaoRevisor(
            dano=Dano.NENHUM,
            destino=Destino.CONFIAVEL,
            decisao=DecisaoRevisor.PERMITIR,
            motivo="Uma regra sua permite esta ação.",
        )
    return bloqueio("Sem modelo revisor neste contexto; a decisão fica com você.")


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
    from app.core.redacao import limpar_texto_sensivel
    from app.modelos.tabelas import RegistroAcao

    sessao.add(
        RegistroAcao(
            usuario_id=usuario_id,
            agente_id=agente_id,
            etapa_id=etapa_id,
            ferramenta=acao.ferramenta,
            resumo=limpar_texto_sensivel(resumo)[:500],
            aprovacao_id=aprovacao_id,
        )
    )
    await sessao.flush()
