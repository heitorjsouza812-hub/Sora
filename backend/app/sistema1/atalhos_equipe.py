"""Rede de segurança dos pedidos de bot e de grupo feitos à Sora.

Modelos pequenos (gpt-oss-20b, qwen, llama) às vezes respondem "já te mando o cartão" sem chamar
``criar_agente`` ou ``propor_grupo``, ou o provedor responde 429 no meio do turno. O cartão de
rascunho e a proposta de grupo não precisam de modelo (os dois são montados por regra), então, se o
turno terminou sem eles, o worker prepara o cartão pelo mesmo caminho das ferramentas. Nada nasce
sem o aceite do usuário: é só o cartão.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Literal
from uuid import UUID

if TYPE_CHECKING:
    from app.ferramentas.base import ContextoFerramenta

registro = logging.getLogger(__name__)

_CRIAR = re.compile(
    r"\b(crie|criar|cria|monte|montar|forme|formar|preciso|precisamos|quero|queremos|gostaria)\b",
    re.IGNORECASE,
)
_GRUPO = re.compile(
    r"\b(um|uma)\s+(grupo|equipe)\b|\b(grupo|equipe)s?\s+(de|com)\s+(bots?|agentes?)\b",
    re.IGNORECASE,
)
_BOT = re.compile(r"\b(um|uma|novo|nova|outro|outra)\s+(bot|agente)\b", re.IGNORECASE)
_FERRAMENTA = re.compile(r"\bcriar_agente\b", re.IGNORECASE)
_NOME = re.compile(r"\bchamad[oa]\s+([^\W\d_][\w-]{1,39})", re.IGNORECASE)
_PAPEL = re.compile(
    r"\bbot\b(?:\s+chamad[oa]\s+[^\W\d_][\w-]{1,39})?\s+(que|para|de)\s+(.+)", re.IGNORECASE
)

PAPEL_PADRAO = "Assistente geral para as tarefas do dia a dia"
NOME_PADRAO = "Assistente"


def intencao_de_equipe(pedido: str) -> Literal["bot", "grupo"] | None:
    """O pedido quer criar um bot ou montar um grupo? ``None`` para o resto (inclusive delegar a
    um bot ou grupo que já existe)."""
    if _CRIAR.search(pedido) and _GRUPO.search(pedido):
        return "grupo"
    if _FERRAMENTA.search(pedido) or (_CRIAR.search(pedido) and _BOT.search(pedido)):
        return "bot"
    return None


def nome_e_papel_do_bot(pedido: str) -> tuple[str, str]:
    """Nome e papel provisórios; o usuário ajusta tudo no cartão de rascunho."""
    achou_nome = _NOME.search(pedido)
    nome = achou_nome.group(1).strip() if achou_nome else NOME_PADRAO
    papel = PAPEL_PADRAO
    achou_papel = _PAPEL.search(pedido)
    if achou_papel:
        ligacao = achou_papel.group(1).lower()
        resto = achou_papel.group(2).strip().rstrip(".!?").strip()
        if resto and not re.match(r"(mim|n[óo]s|voc[êe])\b", resto, re.IGNORECASE):
            papel = resto[:1].upper() + resto[1:] if ligacao == "que" else f"Bot {ligacao} {resto}"
    return nome[:40], papel[:2_000]


async def contar_cartoes(usuario_id: UUID) -> int:
    """Rascunhos de bot e propostas de grupo do usuário (para saber se o turno criou algum)."""
    from sqlalchemy import func, select

    from app.core.banco import fabrica_sessoes
    from app.modelos.tabelas import PropostaGrupo, RascunhoBot

    async with fabrica_sessoes()() as sessao:
        rascunhos = await sessao.scalar(
            select(func.count())
            .select_from(RascunhoBot)
            .where(RascunhoBot.usuario_id == usuario_id)
        )
        propostas = await sessao.scalar(
            select(func.count())
            .select_from(PropostaGrupo)
            .where(PropostaGrupo.usuario_id == usuario_id)
        )
    return (rascunhos or 0) + (propostas or 0)


async def garantir_cartao(
    contexto: ContextoFerramenta, pedido: str, cartoes_antes: int
) -> Literal["bot", "grupo"] | None:
    """Se o turno terminou sem o cartão de bot/grupo, prepara-o agora. Devolve o que preparou."""
    intencao = intencao_de_equipe(pedido)
    if intencao is None:
        return None
    if await contar_cartoes(contexto.usuario_id) > cartoes_antes:
        return None  # a Sora (o modelo) já preparou
    if intencao == "grupo":
        from app.ferramentas.propor_grupo import ProporGrupo, propor_grupo

        await propor_grupo(ProporGrupo(pedido=pedido[:20_000]), contexto)
    else:
        from app.ferramentas.criar_agente import CriarAgente, criar_agente

        nome, papel = nome_e_papel_do_bot(pedido)
        await criar_agente(CriarAgente(nome=nome, papel=papel), contexto)
    registro.info("cartão de %s preparado pela rede de segurança", intencao)
    return intencao
