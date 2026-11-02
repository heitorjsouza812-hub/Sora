"""Entregas e versões (especificação §1, tabela ``entregas``; §2, rotas
``/entregas`` e ``/aprovar`` e evento ``entrega``; §3.2, Revisão).

Cada chamada a ``entregar`` vira uma linha em ``entregas`` com a versão da
cadeia. A Revisão compara ``versao`` com ``versao - 1``; Aprovar grava
``conversas.aprovada_versao``.

Toda leitura e escrita por conversa recebe ``usuario_id`` (obrigatório, só por nome) e filtra
por ``conversas.usuario_id``: conversa de outro usuário = "não encontrada" (API-10, IDOR).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select

from app.core.banco import fabrica_sessoes
from app.modelos.enumeracoes import TipoEntrega
from app.modelos.tabelas import Conversa, Entrega


@dataclass(frozen=True, slots=True)
class NovaEntrega:
    """Dados para gravar uma entrega."""

    usuario_id: UUID
    conversa_id: UUID
    cadeia_id: UUID
    etapa_id: UUID | None
    agente_id: UUID | None
    versao: int
    tipo: TipoEntrega
    titulo: str
    resumo: str
    conteudo: dict[str, Any]


async def registrar_entrega(entrega: NovaEntrega) -> UUID:
    """Grava a entrega e emite o evento ``entrega``."""
    async with fabrica_sessoes()() as sessao:
        conversa = await sessao.get(Conversa, entrega.conversa_id)
        if conversa is None or conversa.usuario_id != entrega.usuario_id:
            raise LookupError("conversa nao encontrada")
        linha = Entrega(
            usuario_id=entrega.usuario_id,
            conversa_id=entrega.conversa_id,
            cadeia_id=entrega.cadeia_id,
            etapa_id=entrega.etapa_id,
            agente_id=entrega.agente_id,
            versao=entrega.versao,
            tipo=entrega.tipo,
            titulo=entrega.titulo,
            resumo=entrega.resumo,
            conteudo=entrega.conteudo,
        )
        sessao.add(linha)
        await sessao.commit()
        return linha.id


async def versoes_da_conversa(conversa_id: UUID, *, usuario_id: UUID) -> list[int]:
    """Lista as versões que têm entregas, da mais nova para a mais antiga (só do dono)."""
    async with fabrica_sessoes()() as sessao:
        conversa = await sessao.get(Conversa, conversa_id)
        if conversa is None or conversa.usuario_id != usuario_id:
            raise LookupError("conversa nao encontrada")
        consulta = (
            select(Entrega.versao)
            .where(Entrega.conversa_id == conversa_id, Entrega.usuario_id == usuario_id)
            .distinct()
            .order_by(desc(Entrega.versao))
        )
        return list((await sessao.scalars(consulta)).all())


async def entregas_da_versao(
    conversa_id: UUID, versao: int | None = None, *, usuario_id: UUID
) -> list[dict[str, Any]]:
    """Entregas de uma versão (padrão: a mais nova), só se a conversa for do usuário."""
    async with fabrica_sessoes()() as sessao:
        conversa = await sessao.get(Conversa, conversa_id)
        if conversa is None or conversa.usuario_id != usuario_id:
            raise LookupError("conversa nao encontrada")
        if versao is None:
            versao = await sessao.scalar(
                select(Entrega.versao)
                .where(Entrega.conversa_id == conversa_id, Entrega.usuario_id == usuario_id)
                .order_by(desc(Entrega.versao))
                .limit(1)
            )
        if versao is None:
            return []
        linhas = (
            await sessao.scalars(
                select(Entrega)
                .where(
                    Entrega.conversa_id == conversa_id,
                    Entrega.usuario_id == usuario_id,
                    Entrega.versao == versao,
                )
                .order_by(Entrega.criada_em, Entrega.id)
            )
        ).all()
        return [
            {
                "id": linha.id,
                "agente_id": linha.agente_id,
                "versao": linha.versao,
                "tipo": linha.tipo,
                "titulo": linha.titulo,
                "resumo": linha.resumo,
                "conteudo": linha.conteudo,
                "criada_em": linha.criada_em,
            }
            for linha in linhas
        ]


async def aprovar_versao(conversa_id: UUID, versao: int, *, usuario_id: UUID) -> None:
    """Grava ``conversas.aprovada_versao`` (só do dono) e emite ``conversa.atualizada``."""
    async with fabrica_sessoes()() as sessao:
        conversa = await sessao.get(Conversa, conversa_id, with_for_update=True)
        if conversa is None or conversa.usuario_id != usuario_id:
            raise LookupError("conversa nao encontrada")
        existe = await sessao.scalar(
            select(Entrega.id).where(
                Entrega.conversa_id == conversa_id,
                Entrega.usuario_id == usuario_id,
                Entrega.versao == versao,
            )
        )
        if existe is None:
            raise LookupError("versao nao encontrada")
        conversa.aprovada_versao = versao
        await sessao.commit()
