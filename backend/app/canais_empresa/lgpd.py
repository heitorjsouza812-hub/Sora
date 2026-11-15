"""LGPD: "apagar tudo deste cliente" e retenção da mensagem crua.

Apagar um cliente remove o contato, as mensagens, a ficha e os rastros dele no conhecimento da
empresa (origens e contagem; item que ficar sem nenhuma ocorrência sai da base).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.canais_empresa.tabelas import (
    ConhecimentoEmpresa,
    ContatoEmpresa,
    FatoCliente,
    MensagemEmpresa,
)

RETENCAO_PADRAO_DIAS = 90
RETENCAO_FATOS_PADRAO_DIAS = 365
RETENCAO_MIN_DIAS = 1
RETENCAO_MAX_DIAS = 3650


async def apagar_cliente(
    sessao: AsyncSession, usuario_id: UUID, contato_id: UUID
) -> dict[str, int] | None:
    """Apaga tudo do contato. ``None`` se ele não existe ou é de outra conta."""
    contato = await sessao.scalar(
        select(ContatoEmpresa).where(
            ContatoEmpresa.id == contato_id, ContatoEmpresa.usuario_id == usuario_id
        )
    )
    if contato is None:
        return None
    fatos = (
        await sessao.scalar(
            select(func.count())
            .select_from(FatoCliente)
            .where(FatoCliente.contato_id == contato_id, FatoCliente.usuario_id == usuario_id)
        )
        or 0
    )
    mensagens = (
        await sessao.scalar(
            select(func.count())
            .select_from(MensagemEmpresa)
            .where(
                MensagemEmpresa.contato_id == contato_id, MensagemEmpresa.usuario_id == usuario_id
            )
        )
        or 0
    )
    limpos = removidos = 0
    afetados = (
        await sessao.scalars(
            select(ConhecimentoEmpresa).where(
                ConhecimentoEmpresa.usuario_id == usuario_id,
                ConhecimentoEmpresa.origens.contains([{"contato_id": str(contato_id)}]),
            )
        )
    ).all()
    for item in afetados:
        restantes = [o for o in item.origens if o.get("contato_id") != str(contato_id)]
        tirados = len(item.origens) - len(restantes)
        item.ocorrencias = max(0, item.ocorrencias - tirados)
        if item.ocorrencias == 0 or not restantes:
            await sessao.delete(item)
            removidos += 1
        else:
            item.origens = restantes
            item.atualizado_em = datetime.now(UTC)
            limpos += 1
    await sessao.flush()
    await sessao.execute(
        delete(ContatoEmpresa).where(
            ContatoEmpresa.id == contato_id, ContatoEmpresa.usuario_id == usuario_id
        )
    )
    return {
        "mensagens": mensagens,
        "fatos": fatos,
        "conhecimento_limpo": limpos,
        "conhecimento_removido": removidos,
    }


async def apagar_mensagens_vencidas(sessao: AsyncSession, agora: datetime | None = None) -> int:
    """Rotina de retenção: tira o texto cru das mensagens mais velhas que o prazo do usuário
    (padrão 90 dias, contados do recebimento). A linha fica, sem texto, para a idempotência do
    webhook e para o link de origem dos fatos. Devolve quantas mensagens perderam o texto."""
    resultado = await sessao.execute(
        text(
            """
            UPDATE ce_mensagens m
               SET texto = NULL,
                   texto_apagado_em = :agora,
                   processada_em = COALESCE(m.processada_em, :agora)
             WHERE m.texto IS NOT NULL
               AND m.recebida_em < :agora - make_interval(
                     days => COALESCE(
                       (SELECT p.retencao_dias FROM ce_preferencias p
                         WHERE p.usuario_id = m.usuario_id), :padrao))
            """
        ).bindparams(agora=agora or datetime.now(UTC), padrao=RETENCAO_PADRAO_DIAS)
    )
    return resultado.rowcount or 0


async def apagar_fatos_vencidos(sessao: AsyncSession, agora: datetime | None = None) -> int:
    """Retenção dos fatos da ficha (Prumo B5): apaga o fato mais velho que ``retencao_fatos_dias``
    do usuário (padrão 365, contados da criação; sem exceção para fato editado, porque o prazo
    é do dado pessoal). O contato e as mensagens seguem as próprias regras; "apagar cliente"
    continua apagando tudo na hora. Devolve quantos fatos saíram."""
    resultado = await sessao.execute(
        text(
            """
            DELETE FROM ce_fatos f
             WHERE f.criado_em < :agora - make_interval(
                     days => COALESCE(
                       (SELECT p.retencao_fatos_dias FROM ce_preferencias p
                         WHERE p.usuario_id = f.usuario_id), :padrao))
            """
        ).bindparams(agora=agora or datetime.now(UTC), padrao=RETENCAO_FATOS_PADRAO_DIAS)
    )
    return resultado.rowcount or 0
