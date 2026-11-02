"""Despacho real da fila e dos canais de equipe."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage
from sqlalchemy import select

from app.canais_equipe.contexto import montar_pacote
from app.canais_equipe.roteamento import DecisaoLider, Membro, conferir_decisao
from app.canais_equipe.servico import Mudancas, ServicoCanais
from app.canais_equipe.sql import ArmazemCanaisSQL
from app.eventos.equipe import (
    FilaAtualizada,
    ItemFilaResumo,
    MensagemCanalEvento,
    TarefaCanalAtualizada,
    acoes_da_tarefa,
    publicar_evento_equipe,
)
from app.filas import FilaAgente
from app.filas.sql import ArmazemFilaSQL
from app.llm.falso import modelo_falso_ativo
from app.modelos.tabelas import Agente, CanalEquipe
from app.orquestrador.modelos import modelos_do_papel
from workers.fila import enfileirar

registro = logging.getLogger(__name__)


def _tarefa_evento(tarefa) -> TarefaCanalAtualizada:
    return TarefaCanalAtualizada(
        canal_id=tarefa.canal_id,
        tarefa_id=tarefa.id,
        dono_id=tarefa.dono_id,
        pai_id=tarefa.pai_id,
        status=tarefa.status.value,
        motivo=tarefa.motivo.value if tarefa.motivo else None,
        revisao=tarefa.revisao,
        acoes=acoes_da_tarefa(tarefa.status.value),
    )


def _mensagem_evento(mensagem) -> MensagemCanalEvento:
    return MensagemCanalEvento(
        canal_id=mensagem.canal_id,
        mensagem_id=mensagem.id,
        seq=mensagem.seq,
        autor=mensagem.autor.value,
        agente_id=mensagem.agente_id,
        tipo=mensagem.tipo.value,
        texto=mensagem.texto,
        responde_a=mensagem.responde_a,
        tarefa_id=mensagem.tarefa_id,
        anexos=list(mensagem.anexos),
        criada_em=mensagem.criada_em,
    )


async def _publicar_mudancas(ctx: dict[str, Any], usuario_id: UUID, mudancas: Mudancas) -> None:
    for mensagem in mudancas.mensagens:
        await publicar_evento_equipe(ctx["redis_eventos"], _mensagem_evento(mensagem), usuario_id)
    for tarefa in mudancas.tarefas:
        await publicar_evento_equipe(ctx["redis_eventos"], _tarefa_evento(tarefa), usuario_id)


async def _membros(sessao, usuario_id: UUID, ids: list[UUID]) -> list[Membro]:
    agentes = (
        await sessao.scalars(
            select(Agente).where(
                Agente.usuario_id == usuario_id,
                Agente.id.in_(ids),
                Agente.apagado_em.is_(None),
            )
        )
    ).all()
    por_id = {agente.id: agente for agente in agentes}
    return [
        Membro(
            agente_id,
            por_id[agente_id].nome,
            por_id[agente_id].funcao,
            not por_id[agente_id].fila_pausada,
        )
        for agente_id in ids
        if agente_id in por_id
    ]


async def recuperar_equipe_apos_queda(ctx: dict[str, Any]) -> None:
    """Startup: persiste a recuperacao antes de o worker aceitar novos turnos."""
    async with ctx["sessoes"]() as sessao:
        fila = FilaAgente(ArmazemFilaSQL(sessao))
        interrompidos = await fila.recuperar_apos_queda()
        canais = ServicoCanais(ArmazemCanaisSQL(sessao))
        tarefas = await canais.recuperar_apos_queda()
        usuarios_canais = {
            canal.id: canal.usuario_id
            for canal in (
                await sessao.scalars(
                    select(CanalEquipe).where(
                        CanalEquipe.id.in_({tarefa.canal_id for tarefa in tarefas})
                    )
                )
            ).all()
        }
        await sessao.commit()
    for item in interrompidos:
        await publicar_evento_equipe(
            ctx["redis_eventos"],
            FilaAtualizada(
                agente_id=item.agente_id,
                pausada=False,
                limite_tarefas=2,
                itens=[
                    ItemFilaResumo(
                        item_id=item.id,
                        seq=item.seq,
                        pista=item.pista,
                        origem=item.origem.value,
                        previa=item.texto[:200],
                        status=item.status.value,
                    )
                ],
            ),
            item.usuario_id,
        )
    for tarefa in tarefas:
        await publicar_evento_equipe(
            ctx["redis_eventos"],
            _tarefa_evento(tarefa),
            usuarios_canais[tarefa.canal_id],
        )


async def _rotear_com_lider(ctx: dict[str, Any], canal_id: UUID) -> None:
    async with ctx["sessoes"]() as sessao:
        armazem = ArmazemCanaisSQL(sessao)
        servico = ServicoCanais(armazem)
        canal = await servico.canal(canal_id)
        if canal.lider_id is None:
            return
        pendentes = await servico.pedidos_para_rotear_com_lider(canal_id, canal.usuario_id)
        membros = await _membros(sessao, canal.usuario_id, canal.membros)
        mensagens = {m.id: m for m in await armazem.mensagens(canal.id)}
        tarefas = await armazem.tarefas(canal.id)
        await sessao.commit()
    for mensagem_id in pendentes:
        mensagem = mensagens.get(mensagem_id)
        if mensagem is None:
            continue
        if modelo_falso_ativo():
            bruto = {"acao": "atribuir", "agentes": [str(canal.lider_id)]}
        else:
            async with ctx["sessoes"]() as sessao:
                modelos = await modelos_do_papel(
                    sessao, canal.usuario_id, "individual", dificuldade=1
                )
            modelo = modelos[0].with_structured_output(DecisaoLider)
            bruto = await modelo.ainvoke(
                [
                    HumanMessage(
                        "Escolha quem responde neste canal.\n"
                        + "\n".join(f"- {m.nome} ({m.funcao}): {m.id}" for m in membros)
                        + f"\nPedido: {mensagem.texto}"
                    )
                ]
            )
            bruto = bruto.model_dump(mode="json")
        decisao = conferir_decisao(bruto, membros=membros, tarefas=tarefas, texto=mensagem.texto)
        async with ctx["sessoes"]() as sessao:
            servico = ServicoCanais(ArmazemCanaisSQL(sessao))
            mudancas = await servico.decisao_do_lider(
                canal_id, canal.usuario_id, mensagem_id, decisao
            )
            await sessao.commit()
        await _publicar_mudancas(ctx, canal.usuario_id, mudancas)


async def _executar_tarefa(ctx: dict[str, Any], tarefa_id: UUID) -> None:
    async with ctx["sessoes"]() as sessao:
        armazem = ArmazemCanaisSQL(sessao)
        servico = ServicoCanais(armazem)
        async with armazem.transacao_tarefa(tarefa_id):
            tarefa = await servico.iniciar(tarefa_id)
        canal = await servico.canal(tarefa.canal_id)
        membros = await _membros(sessao, canal.usuario_id, canal.membros)
        mensagens = await armazem.mensagens(canal.id)
        tarefas = await armazem.tarefas(canal.id)
        pacote = montar_pacote(
            canal=canal,
            tarefa=tarefa,
            agente_id=tarefa.dono_id,
            membros=membros,
            mensagens=mensagens,
            tarefas=tarefas,
        )
        revisao = tarefa.revisao
        await sessao.commit()
    await publicar_evento_equipe(ctx["redis_eventos"], _tarefa_evento(tarefa), canal.usuario_id)
    try:
        if modelo_falso_ativo():
            async with ctx["sessoes"]() as sessao:
                armazem = ArmazemCanaisSQL(sessao)
                async with armazem.transacao_tarefa(tarefa_id):
                    mudancas = await ServicoCanais(armazem).registrar_resultado(
                        tarefa_id,
                        revisao,
                        por_agente=tarefa.dono_id,
                        texto="Resultado real do turno do modelo falso no canal.",
                    )
                await sessao.commit()
        else:
            from app.agentes import ContextoAgente, montar_e_rodar_agente

            async with ctx["sessoes"]() as sessao:
                modelos = await modelos_do_papel(
                    sessao, canal.usuario_id, "individual", dificuldade=2
                )
            contexto = ContextoAgente(
                usuario_id=canal.usuario_id,
                agente_id=tarefa.dono_id,
                conversa_id=canal.id,
                papel="canal",
                canal_id=canal.id,
                tarefa_canal_id=tarefa.id,
                revisao_canal=revisao,
                valores_do_prompt={"perfil_do_agente": pacote},
            )
            await montar_e_rodar_agente(
                contexto=contexto,
                modelos=modelos,
                checkpointer=ctx["checkpointer"],
                entrada={"messages": [HumanMessage(pacote)]},
            )
            async with ctx["sessoes"]() as sessao:
                armazem = ArmazemCanaisSQL(sessao)
                async with armazem.transacao_tarefa(tarefa_id):
                    mudancas = await ServicoCanais(armazem).fim_do_turno(tarefa_id, revisao)
                await sessao.commit()
    except Exception as erro:
        registro.exception("turno do canal %s falhou", tarefa_id)
        async with ctx["sessoes"]() as sessao:
            armazem = ArmazemCanaisSQL(sessao)
            async with armazem.transacao_tarefa(tarefa_id):
                mudancas = await ServicoCanais(armazem).falhar(
                    tarefa_id, revisao, type(erro).__name__
                )
            await sessao.commit()
    await _publicar_mudancas(ctx, canal.usuario_id, mudancas)
    await enfileirar("despachar_equipe", canal_id=str(canal.id))


async def despachar_equipe(
    ctx: dict[str, Any], canal_id: str | None = None, agente_id: str | None = None
) -> None:
    """Consulta a fila antes do turno e ocupa as vagas dos canais."""
    if agente_id is not None:
        async with ctx["sessoes"]() as sessao:
            fila = FilaAgente(ArmazemFilaSQL(sessao))
            liberacao = await fila.proximos(UUID(agente_id))
        for item in liberacao.iniciar:
            await enfileirar(
                "executar_item_fila", item_id=str(item.id), agente_id=str(item.agente_id)
            )
    if canal_id is None:
        return
    canal_uuid = UUID(canal_id)
    await _rotear_com_lider(ctx, canal_uuid)
    async with ctx["sessoes"]() as sessao:
        proximas = await ServicoCanais(ArmazemCanaisSQL(sessao)).proximas(canal_uuid)
    for tarefa in proximas:
        await enfileirar("executar_tarefa_canal", tarefa_id=str(tarefa.id))


async def executar_tarefa_canal(ctx: dict[str, Any], tarefa_id: str) -> None:
    await _executar_tarefa(ctx, UUID(tarefa_id))


async def executar_item_fila(ctx: dict[str, Any], item_id: str, agente_id: str) -> None:
    """Reserva e conclui um item; as origens especializadas injetam seu turno antes de concluir."""
    async with ctx["sessoes"]() as sessao:
        fila = FilaAgente(ArmazemFilaSQL(sessao))
        item = await fila.iniciar(UUID(item_id), UUID(agente_id))
        await fila.rodando(item.id, item.agente_id)
        await fila.concluir(item.id, item.agente_id)
        await sessao.commit()
    await enfileirar("despachar_equipe", agente_id=agente_id)
