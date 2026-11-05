"""Despacho real da fila e dos canais de equipe."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from app.canais_equipe.contexto import montar_pacote
from app.canais_equipe.interrupcao import (
    interrupcao_pedida,
    limpar_interrupcao,
    pedir_interrupcao,
)
from app.canais_equipe.modelos import ErroCanal
from app.canais_equipe.roteamento import (
    INSTRUCOES_LIDER,
    DecisaoLider,
    Membro,
    conferir_decisao,
)
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
from app.filas import ErroFila, FilaAgente
from app.filas.sql import ArmazemFilaSQL
from app.llm.estruturada import com_saida_estruturada, instrucoes_json
from app.llm.falso import modelo_falso_ativo
from app.modelos.tabelas import Agente, CanalEquipe
from app.orquestrador.modelos import modelos_do_papel
from workers.fila import enfileirar
from workers.travados import batimento, batimento_vivo

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
    await pedir_interrupcao(ctx["redis_eventos"], mudancas.interromper)
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

        async def vivo(id_: UUID) -> bool:
            return await batimento_vivo(ctx["redis_eventos"], id_)

        # Só o que não tem batimento: turnos vivos de outros workers não são tocados.
        interrompidos = await fila.recuperar_apos_queda(vivo)
        canais = ServicoCanais(ArmazemCanaisSQL(sessao))
        tarefas = await canais.recuperar_apos_queda(vivo)
        agentes_com_espera = {
            i.agente_id
            for i in await ArmazemFilaSQL(sessao).todos_abertos()
            if i.status.value == "na_fila"
        }
        canais_com_espera = {
            t.canal_id
            for t in await ArmazemCanaisSQL(sessao).tarefas_abertas()
            if t.status.value == "na_fila"
        }
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
    # O que ficou esperando (inclusive 'iniciando' devolvido a fila) volta a andar.
    for agente_id in agentes_com_espera:
        await enfileirar("despachar_equipe", agente_id=str(agente_id))
    for canal_id in canais_com_espera:
        await enfileirar("despachar_equipe", canal_id=str(canal_id))


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
            modelo = com_saida_estruturada(modelos[0], DecisaoLider)
            try:
                resposta = await modelo.ainvoke(
                    [
                        SystemMessage(INSTRUCOES_LIDER + "\n\n" + instrucoes_json(DecisaoLider)),
                        HumanMessage(
                            "Escolha quem responde neste canal.\n"
                            + "\n".join(f"- {m.nome} ({m.funcao}): {m.id}" for m in membros)
                            + f"\nPedido: {mensagem.texto}"
                        ),
                    ]
                )
                bruto = (
                    resposta.model_dump(mode="json")
                    if isinstance(resposta, DecisaoLider)
                    else resposta
                )
            except Exception:
                # sem decisão legível a tarefa para (o usuário reatribui); o canal não trava
                registro.exception("O líder do canal %s não decidiu.", canal_id)
                bruto = ""
        decisao = conferir_decisao(bruto, membros=membros, tarefas=tarefas, texto=mensagem.texto)
        async with ctx["sessoes"]() as sessao:
            servico = ServicoCanais(ArmazemCanaisSQL(sessao))
            mudancas = await servico.decisao_do_lider(
                canal_id, canal.usuario_id, mensagem_id, decisao
            )
            await sessao.commit()
        await _publicar_mudancas(ctx, canal.usuario_id, mudancas)


async def _turno_falso(ctx: dict[str, Any], tarefa, revisao: int) -> Mudancas:
    """Turno do modelo falso (desenvolvimento e testes): responde na hora."""
    async with ctx["sessoes"]() as sessao:
        armazem = ArmazemCanaisSQL(sessao)
        async with armazem.transacao_tarefa(tarefa.id):
            mudancas = await ServicoCanais(armazem).registrar_resultado(
                tarefa.id,
                revisao,
                por_agente=tarefa.dono_id,
                texto="Resultado real do turno do modelo falso no canal.",
            )
        await sessao.commit()
    return mudancas


async def _turno_real(ctx: dict[str, Any], tarefa, canal, revisao: int, pacote: str) -> Mudancas:
    from app.agentes import ContextoAgente, montar_e_rodar_agente

    async with ctx["sessoes"]() as sessao:
        modelos = await modelos_do_papel(sessao, canal.usuario_id, "individual", dificuldade=2)
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
        async with armazem.transacao_tarefa(tarefa.id):
            mudancas = await ServicoCanais(armazem).fim_do_turno(tarefa.id, revisao)
        await sessao.commit()
    return mudancas


INTERVALO_VIGIA_S = 0.5
"""De quanto em quanto tempo o worker confere se pediram para parar o turno."""


async def _vigiar_interrupcao(redis: Any, tarefa_id: UUID) -> None:
    while not await interrupcao_pedida(redis, tarefa_id):  # noqa: ASYNC110
        await asyncio.sleep(INTERVALO_VIGIA_S)


async def _rodar_ate_interromper(redis: Any, tarefa_id: UUID, turno) -> Any | None:
    """Roda o turno; se pedirem Parar/Cancelar/Arquivar, cancela o turno de verdade e devolve
    ``None``. Cancelamento vindo de fora (worker desligando) continua propagando."""
    tarefa_turno = asyncio.ensure_future(turno)
    vigia = asyncio.create_task(_vigiar_interrupcao(redis, tarefa_id))
    try:
        await asyncio.wait({tarefa_turno, vigia}, return_when=asyncio.FIRST_COMPLETED)
        if tarefa_turno.done():
            return tarefa_turno.result()
        tarefa_turno.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await tarefa_turno
        return None
    finally:
        vigia.cancel()
        if not tarefa_turno.done():
            tarefa_turno.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await vigia


async def _executar_tarefa(ctx: dict[str, Any], tarefa_id: UUID) -> None:
    # O batimento começa antes de reservar a tarefa: outro worker que suba agora a vê viva.
    async with batimento(ctx["redis_eventos"], tarefa_id):
        await _executar_tarefa_viva(ctx, tarefa_id)


async def _executar_tarefa_viva(ctx: dict[str, Any], tarefa_id: UUID) -> None:
    async with ctx["sessoes"]() as sessao:
        armazem = ArmazemCanaisSQL(sessao)
        servico = ServicoCanais(armazem)
        try:
            async with armazem.transacao_tarefa(tarefa_id):
                tarefa = await servico.iniciar(tarefa_id)
        except ErroCanal as erro:
            # Arquivada, cancelada ou parada depois de entrar na fila do ARQ: não há o que
            # fazer, e levantar faria o ARQ tentar de novo.
            registro.info("tarefa de canal %s ignorada: %s", tarefa_id, erro)
            return
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
    redis = ctx["redis_eventos"]
    await limpar_interrupcao(redis, tarefa_id)  # um pedido antigo não mata este turno novo
    await publicar_evento_equipe(redis, _tarefa_evento(tarefa), canal.usuario_id)
    try:
        if modelo_falso_ativo():
            turno = _turno_falso(ctx, tarefa, revisao)
        else:
            turno = _turno_real(ctx, tarefa, canal, revisao, pacote)
        mudancas = await _rodar_ate_interromper(redis, tarefa_id, turno)
        if mudancas is None:
            registro.info("turno da tarefa de canal %s interrompido a pedido", tarefa_id)
            await limpar_interrupcao(redis, tarefa_id)
            await enfileirar("despachar_equipe", canal_id=str(canal.id))
            return  # quem pediu já gravou o estado (parada/cancelada) e publicou o evento
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
    """Reserva o item, roda o turno do agente de verdade e conclui (ou marca a falha)."""
    from workers.conversa import rodar_turno_do_item

    async with batimento(ctx["redis_eventos"], UUID(item_id)):
        async with ctx["sessoes"]() as sessao:
            fila = FilaAgente(ArmazemFilaSQL(sessao))
            try:
                item = await fila.iniciar(UUID(item_id), UUID(agente_id))
            except ErroFila as erro:
                # Outro despacho já levou o item, ou ainda não é a vez dele (agente ocupado,
                # fila pausada): quem terminar o item dispara o próximo despacho.
                registro.info("item %s da fila ignorado: %s", item_id, erro)
                return
            await fila.rodando(item.id, item.agente_id)
            await sessao.commit()
        try:
            await rodar_turno_do_item(ctx, item)
        except BaseException as erro:
            async with ctx["sessoes"]() as sessao:
                await FilaAgente(ArmazemFilaSQL(sessao)).falhar(
                    item.id, item.agente_id, type(erro).__name__
                )
                await sessao.commit()
            if isinstance(erro, Exception):
                registro.exception("turno do item %s falhou", item_id)
                await enfileirar("despachar_equipe", agente_id=agente_id)
                return
            raise
        async with ctx["sessoes"]() as sessao:
            await FilaAgente(ArmazemFilaSQL(sessao)).concluir(item.id, item.agente_id)
            await sessao.commit()
    await enfileirar("despachar_equipe", agente_id=agente_id)
