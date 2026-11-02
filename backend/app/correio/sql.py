"""Persistencia PostgreSQL de reacoes e transferencias entre agentes."""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.correio.reacoes import Reacao
from app.correio.transferencias import StatusTransferencia, Transferencia
from app.modelos.tabelas import Reacao as ReacaoTabela
from app.modelos.tabelas import TransferenciaArquivo


class ArmazemReacoesSQL:
    def __init__(self, sessao: AsyncSession, usuario_id: UUID) -> None:
        self.sessao, self.usuario_id = sessao, usuario_id

    async def da_mensagem(self, mensagem_id: UUID) -> list[Reacao]:
        linhas = (
            await self.sessao.scalars(
                select(ReacaoTabela)
                .where(
                    ReacaoTabela.usuario_id == self.usuario_id,
                    ReacaoTabela.mensagem_id == mensagem_id,
                )
                .order_by(ReacaoTabela.criada_em, ReacaoTabela.id)
            )
        ).all()
        return [Reacao(r.mensagem_id, r.autor, r.agente_id, r.emoji, r.criada_em) for r in linhas]

    async def adicionar(self, reacao: Reacao) -> None:
        await self.sessao.execute(
            insert(ReacaoTabela)
            .values(
                usuario_id=self.usuario_id,
                mensagem_id=reacao.mensagem_id,
                autor=reacao.autor,
                agente_id=reacao.agente_id,
                emoji=reacao.emoji,
                criada_em=reacao.criada_em,
            )
            .on_conflict_do_nothing()
        )
        await self.sessao.flush()

    async def remover(self, reacao: Reacao) -> None:
        condicoes = [
            ReacaoTabela.usuario_id == self.usuario_id,
            ReacaoTabela.mensagem_id == reacao.mensagem_id,
            ReacaoTabela.autor == reacao.autor,
            ReacaoTabela.emoji == reacao.emoji,
        ]
        condicoes.append(
            ReacaoTabela.agente_id == reacao.agente_id
            if reacao.agente_id
            else ReacaoTabela.agente_id.is_(None)
        )
        await self.sessao.execute(delete(ReacaoTabela).where(*condicoes))
        await self.sessao.flush()


class ArmazemTransferenciasSQL:
    def __init__(self, sessao: AsyncSession) -> None:
        self.sessao = sessao

    async def gravar(self, transferencia: Transferencia) -> None:
        valores = asdict(transferencia)
        valores.pop("caminho_destino", None)
        valores["status"] = transferencia.status.value
        await self.sessao.execute(
            insert(TransferenciaArquivo)
            .values(**valores)
            .on_conflict_do_update(
                index_elements=[TransferenciaArquivo.id],
                set_={k: v for k, v in valores.items() if k != "id"},
            )
        )
        await self.sessao.flush()

    async def recebidas(self, agente_id: UUID) -> list[Transferencia]:
        linhas = (
            await self.sessao.scalars(
                select(TransferenciaArquivo)
                .where(TransferenciaArquivo.para_agente_id == agente_id)
                .order_by(TransferenciaArquivo.criada_em, TransferenciaArquivo.id)
            )
        ).all()
        return [
            Transferencia(
                id=r.id,
                usuario_id=r.usuario_id,
                anexo_id=r.anexo_id,
                de_agente_id=r.de_agente_id,
                para_agente_id=r.para_agente_id,
                nome=r.nome,
                tipo=r.tipo,
                tamanho=r.tamanho,
                imagem=r.imagem,
                status=StatusTransferencia(r.status),
                sha256=r.sha256,
                novo_anexo_id=r.novo_anexo_id,
                erro=r.erro,
                criada_em=r.criada_em,
            )
            for r in linhas
        ]
