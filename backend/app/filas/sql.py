"""Persistencia PostgreSQL da fila de cada agente."""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.filas import EstadoFila, ItemFila, OrigemItem, StatusItem
from app.modelos.tabelas import Agente, FilaMensagem


def _item(linha: FilaMensagem) -> ItemFila:
    return ItemFila(
        id=linha.id,
        usuario_id=linha.usuario_id,
        agente_id=linha.agente_id,
        seq=linha.seq,
        pista=linha.pista,
        origem=OrigemItem(linha.origem),
        texto=linha.texto,
        anexos=tuple(linha.anexos),
        de_agente_id=linha.de_agente_id,
        responde_a=linha.responde_a,
        salto=linha.salto,
        chave=linha.chave,
        status=StatusItem(linha.status),
        em_edicao_por=linha.em_edicao_por,
        motivo=linha.motivo,
        criado_em=linha.criado_em,
        iniciado_em=linha.iniciado_em,
        terminado_em=linha.terminado_em,
    )


class ArmazemFilaSQL:
    """Adaptador transacional; a sessao pertence a rota ou ao job do worker."""

    def __init__(self, sessao: AsyncSession) -> None:
        self.sessao = sessao

    async def estado(self, agente_id: UUID) -> EstadoFila:
        agente = await self.sessao.get(Agente, agente_id)
        if agente is None:
            return EstadoFila(agente_id)
        return EstadoFila(agente.id, agente.fila_pausada, agente.limite_tarefas)

    async def salvar_estado(self, estado: EstadoFila) -> None:
        agente = await self.sessao.get(Agente, estado.agente_id, with_for_update=True)
        if agente is None:
            raise LookupError("Agente nao encontrado.")
        agente.fila_pausada = estado.pausada
        agente.limite_tarefas = estado.limite_tarefas
        await self.sessao.flush()

    async def travar_agente(self, agente_id: UUID) -> None:
        await self.sessao.scalar(select(Agente.id).where(Agente.id == agente_id).with_for_update())

    async def itens(self, agente_id: UUID) -> list[ItemFila]:
        linhas = (
            await self.sessao.scalars(
                select(FilaMensagem)
                .where(FilaMensagem.agente_id == agente_id)
                .order_by(FilaMensagem.seq, FilaMensagem.id)
            )
        ).all()
        return [_item(linha) for linha in linhas]

    async def por_chave(self, agente_id: UUID, chave: str) -> ItemFila | None:
        linha = await self.sessao.scalar(
            select(FilaMensagem).where(
                FilaMensagem.agente_id == agente_id, FilaMensagem.chave == chave
            )
        )
        return _item(linha) if linha else None

    async def proximo_seq(self, agente_id: UUID) -> int:
        # Serializa produtores do mesmo agente; evita dois itens com o mesmo seq.
        await self.sessao.scalar(select(Agente.id).where(Agente.id == agente_id).with_for_update())
        atual = await self.sessao.scalar(
            select(func.coalesce(func.max(FilaMensagem.seq), 0)).where(
                FilaMensagem.agente_id == agente_id
            )
        )
        return int(atual or 0) + 1

    async def gravar(self, item: ItemFila) -> None:
        valores = asdict(item)
        valores["origem"] = item.origem.value
        valores["status"] = item.status.value
        valores["anexos"] = list(item.anexos)
        comando = insert(FilaMensagem).values(**valores)
        comando = comando.on_conflict_do_update(
            index_elements=[FilaMensagem.id],
            set_={chave: valor for chave, valor in valores.items() if chave != "id"},
        )
        await self.sessao.execute(comando)
        await self.sessao.flush()

    async def todos_abertos(self) -> list[ItemFila]:
        linhas = (
            await self.sessao.scalars(
                select(FilaMensagem)
                .where(FilaMensagem.status.in_(["na_fila", "iniciando", "rodando"]))
                .order_by(FilaMensagem.agente_id, FilaMensagem.seq)
            )
        ).all()
        return [_item(linha) for linha in linhas]
