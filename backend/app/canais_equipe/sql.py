"""Persistencia PostgreSQL dos canais e de suas tarefas."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.canais_equipe.modelos import (
    ABERTAS,
    AutorCanal,
    Canal,
    MensagemCanal,
    MotivoParada,
    StatusTarefa,
    TarefaCanal,
    TipoMensagemCanal,
)
from app.modelos.tabelas import CanalEquipe, MembroCanal, MensagemCanalTabela, TarefaCanalTabela


def _canal(linha: CanalEquipe, membros: list[UUID]) -> Canal:
    return Canal(
        id=linha.id,
        usuario_id=linha.usuario_id,
        nome=linha.nome,
        membros=membros,
        lider_id=linha.lider_id,
        proposito=linha.proposito,
        instrucoes=linha.instrucoes,
        resumo=linha.resumo,
        resumo_ate_seq=linha.resumo_ate_seq,
        pedidos_sem_lider=list(linha.pedidos_sem_lider),
        arquivado_em=linha.arquivado_em,
        criado_em=linha.criado_em,
    )


def _mensagem(linha: MensagemCanalTabela) -> MensagemCanal:
    return MensagemCanal(
        id=linha.id,
        canal_id=linha.canal_id,
        seq=linha.seq,
        autor=AutorCanal(linha.autor),
        texto=linha.texto,
        agente_id=linha.agente_id,
        tipo=TipoMensagemCanal(linha.tipo),
        responde_a=linha.responde_a,
        tarefa_id=linha.tarefa_id,
        anexos=tuple(linha.anexos),
        criada_em=linha.criada_em,
    )


def _tarefa(linha: TarefaCanalTabela) -> TarefaCanal:
    return TarefaCanal(
        id=linha.id,
        canal_id=linha.canal_id,
        pedido_id=linha.pedido_id,
        dono_id=linha.dono_id,
        instrucao=linha.instrucao,
        raiz_id=linha.raiz_id,
        pai_id=linha.pai_id,
        delegada_por=linha.delegada_por,
        status=StatusTarefa(linha.status),
        motivo=MotivoParada(linha.motivo) if linha.motivo else None,
        revisao=linha.revisao,
        turno_seq=linha.turno_seq,
        fim_no_turno_do_pai=linha.fim_no_turno_do_pai,
        seguimentos=list(linha.seguimentos),
        resultado=linha.resultado,
        erro=linha.erro,
        criada_em=linha.criada_em,
        atualizada_em=linha.atualizada_em,
    )


class ArmazemCanaisSQL:
    def __init__(self, sessao: AsyncSession) -> None:
        self.sessao = sessao

    async def _membros(self, canal_id: UUID) -> list[UUID]:
        return list(
            (
                await self.sessao.scalars(
                    select(MembroCanal.agente_id)
                    .where(MembroCanal.canal_id == canal_id)
                    .order_by(MembroCanal.ordem, MembroCanal.agente_id)
                )
            ).all()
        )

    async def canal(self, canal_id: UUID) -> Canal | None:
        linha = await self.sessao.get(CanalEquipe, canal_id)
        return _canal(linha, await self._membros(canal_id)) if linha else None

    async def salvar_canal(self, canal: Canal) -> None:
        valores = {
            "id": canal.id,
            "usuario_id": canal.usuario_id,
            "nome": canal.nome,
            "proposito": canal.proposito,
            "instrucoes": canal.instrucoes,
            "lider_id": canal.lider_id,
            "resumo": canal.resumo,
            "resumo_ate_seq": canal.resumo_ate_seq,
            "pedidos_sem_lider": list(canal.pedidos_sem_lider),
            "arquivado_em": canal.arquivado_em,
            "criado_em": canal.criado_em,
        }
        comando = (
            insert(CanalEquipe)
            .values(**valores)
            .on_conflict_do_update(
                index_elements=[CanalEquipe.id],
                set_={
                    k: v for k, v in valores.items() if k not in {"id", "usuario_id", "criado_em"}
                },
            )
        )
        await self.sessao.execute(comando)
        await self.sessao.execute(delete(MembroCanal).where(MembroCanal.canal_id == canal.id))
        self.sessao.add_all(
            [
                MembroCanal(canal_id=canal.id, agente_id=agente_id, ordem=ordem)
                for ordem, agente_id in enumerate(canal.membros)
            ]
        )
        await self.sessao.flush()

    async def canais_do_usuario(self, usuario_id: UUID) -> list[Canal]:
        ids = (
            await self.sessao.scalars(
                select(CanalEquipe.id)
                .where(CanalEquipe.usuario_id == usuario_id)
                .order_by(CanalEquipe.criado_em, CanalEquipe.id)
            )
        ).all()
        return [canal for canal_id in ids if (canal := await self.canal(canal_id)) is not None]

    async def proximo_seq(self, canal_id: UUID) -> int:
        await self.sessao.scalar(
            select(CanalEquipe.id).where(CanalEquipe.id == canal_id).with_for_update()
        )
        atual = await self.sessao.scalar(
            select(func.coalesce(func.max(MensagemCanalTabela.seq), 0)).where(
                MensagemCanalTabela.canal_id == canal_id
            )
        )
        return int(atual or 0) + 1

    async def gravar_mensagem(self, mensagem: MensagemCanal) -> None:
        valores = asdict(mensagem)
        valores["autor"] = mensagem.autor.value
        valores["tipo"] = mensagem.tipo.value
        valores["anexos"] = list(mensagem.anexos)
        comando = (
            insert(MensagemCanalTabela)
            .values(**valores)
            .on_conflict_do_update(
                index_elements=[MensagemCanalTabela.id],
                set_={k: v for k, v in valores.items() if k != "id"},
            )
        )
        await self.sessao.execute(comando)
        await self.sessao.flush()

    async def mensagens(self, canal_id: UUID) -> list[MensagemCanal]:
        linhas = (
            await self.sessao.scalars(
                select(MensagemCanalTabela)
                .where(MensagemCanalTabela.canal_id == canal_id)
                .order_by(MensagemCanalTabela.seq, MensagemCanalTabela.id)
            )
        ).all()
        return [_mensagem(linha) for linha in linhas]

    async def gravar_tarefa(self, tarefa: TarefaCanal) -> None:
        valores = asdict(tarefa)
        valores["status"] = tarefa.status.value
        valores["motivo"] = tarefa.motivo.value if tarefa.motivo else None
        valores["seguimentos"] = list(tarefa.seguimentos)
        comando = (
            insert(TarefaCanalTabela)
            .values(**valores)
            .on_conflict_do_update(
                index_elements=[TarefaCanalTabela.id],
                set_={k: v for k, v in valores.items() if k != "id"},
            )
        )
        await self.sessao.execute(comando)
        await self.sessao.flush()

    async def tarefa(self, tarefa_id: UUID) -> TarefaCanal | None:
        linha = await self.sessao.get(TarefaCanalTabela, tarefa_id)
        return _tarefa(linha) if linha else None

    async def tarefas(self, canal_id: UUID) -> list[TarefaCanal]:
        linhas = (
            await self.sessao.scalars(
                select(TarefaCanalTabela)
                .where(TarefaCanalTabela.canal_id == canal_id)
                .order_by(TarefaCanalTabela.criada_em, TarefaCanalTabela.id)
            )
        ).all()
        return [_tarefa(linha) for linha in linhas]

    async def tarefas_abertas(self) -> list[TarefaCanal]:
        linhas = (
            await self.sessao.scalars(
                select(TarefaCanalTabela)
                .where(TarefaCanalTabela.status.in_([status.value for status in ABERTAS]))
                .order_by(TarefaCanalTabela.canal_id, TarefaCanalTabela.criada_em)
            )
        ).all()
        return [_tarefa(linha) for linha in linhas]

    @asynccontextmanager
    async def transacao_tarefa(self, tarefa_id: UUID) -> AsyncIterator[None]:
        """Trava mae primeiro e depois filha; o chamador executa um turno inteiro dentro."""
        pai_id = await self.sessao.scalar(
            select(TarefaCanalTabela.pai_id).where(TarefaCanalTabela.id == tarefa_id)
        )
        if pai_id is not None:
            await self.sessao.scalar(
                select(TarefaCanalTabela.id).where(TarefaCanalTabela.id == pai_id).with_for_update()
            )
        await self.sessao.scalar(
            select(TarefaCanalTabela.id).where(TarefaCanalTabela.id == tarefa_id).with_for_update()
        )
        yield
