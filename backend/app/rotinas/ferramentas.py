"""Ferramentas ``agendar``, ``listar_agendamentos`` e ``cancelar_agendamento`` de verdade
(os esquemas estão em ``agenda.py``). Rotina sem supervisão não agenda outras rotinas."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.infra import abrir_sessao
from app.modelos.tabelas import Rotina
from app.rotinas import servico
from app.rotinas.agenda import Agendar, CancelarAgendamento, ListarAgendamentos


async def agendar(args: Agendar, contexto: ContextoFerramenta) -> str:
    if contexto.sem_supervisao:
        raise ErroFerramenta("Uma rotina sem supervisão não pode criar outros agendamentos.")
    async with abrir_sessao() as sessao:
        rotina = await servico.criar(
            sessao,
            usuario_id=contexto.usuario_id,
            agente_id=contexto.agente_id,
            conversa_id=contexto.conversa_id,
            args=args,
        )
        quando = rotina.proxima_execucao.isoformat() if rotina.proxima_execucao else "-"
        return f"Agendado (id {rotina.id}). Próxima execução: {quando} ({rotina.fuso})."


async def listar_agendamentos(
    args: ListarAgendamentos, contexto: ContextoFerramenta
) -> list[dict]:
    async with abrir_sessao() as sessao:
        rotinas = await servico.listar(sessao, contexto.usuario_id, contexto.agente_id)
        return [servico.resumo_da_rotina(r) for r in rotinas if r.ativa]


async def cancelar_agendamento(args: CancelarAgendamento, contexto: ContextoFerramenta) -> str:
    if contexto.sem_supervisao:
        raise ErroFerramenta("Uma rotina sem supervisão não pode cancelar agendamentos.")
    try:
        rotina_id = UUID(args.agendamento_id)
    except ValueError as erro:
        raise ErroFerramenta("Id de agendamento inválido.") from erro
    async with abrir_sessao() as sessao:
        rotina = await sessao.scalar(
            select(Rotina).where(
                Rotina.id == rotina_id,
                Rotina.usuario_id == contexto.usuario_id,
                Rotina.agente_id == contexto.agente_id,
            )
        )
        if rotina is None:
            raise ErroFerramenta("Agendamento não encontrado.")
        rotina.ativa = False
        rotina.proxima_execucao = None
    return "Agendamento cancelado."
