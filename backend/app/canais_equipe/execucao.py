"""Adaptadores das ferramentas de canal para banco e eventos reais."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.canais_equipe.ferramentas import (
    CanalDelegar,
    CanalHistorico,
    CanalResultado,
    CanalTransferir,
)
from app.canais_equipe.servico import ServicoCanais
from app.canais_equipe.sql import ArmazemCanaisSQL
from app.core.banco import fabrica_sessoes
from app.eventos.equipe import (
    MensagemCanalEvento,
    TarefaCanalAtualizada,
    acoes_da_tarefa,
    publicar_evento_equipe,
)
from app.ferramentas import ambiente
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.modelos.tabelas import Agente

PAGINAS_DO_HISTORICO = 50
"""Até 10.000 mensagens lidas por chamada (o resultado devolve só as ``limite`` últimas)."""


def _ids(contexto: ContextoFerramenta) -> tuple[UUID, UUID, int]:
    if (
        contexto.canal_id is None
        or contexto.tarefa_canal_id is None
        or contexto.revisao_canal is None
    ):
        raise ErroFerramenta("Esta ferramenta só funciona dentro de uma tarefa de canal.")
    return contexto.canal_id, contexto.tarefa_canal_id, contexto.revisao_canal


def _evento_tarefa(tarefa) -> TarefaCanalAtualizada:
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


async def _publicar_tarefa(contexto: ContextoFerramenta, tarefa) -> None:
    await publicar_evento_equipe(
        ambiente.redis_dos_eventos(), _evento_tarefa(tarefa), contexto.usuario_id
    )


async def canal_historico(args: CanalHistorico, contexto: ContextoFerramenta) -> str:
    canal_id, _, _ = _ids(contexto)
    mensagens = []
    async with fabrica_sessoes()() as sessao:
        servico = ServicoCanais(ArmazemCanaisSQL(sessao))
        # O serviço devolve no máximo 200 por vez, das mais antigas para as mais novas: num canal
        # longo uma só página mostrava só o começo. Anda de página em página até o fim.
        for _ in range(PAGINAS_DO_HISTORICO):
            pagina = await servico.historico(
                canal_id,
                contexto.usuario_id,
                depois_de_seq=mensagens[-1].seq if mensagens else 0,
                limite=200,
            )
            mensagens.extend(pagina)
            if len(pagina) < 200:
                break
    if args.antes_de_seq is not None:
        mensagens = [m for m in mensagens if m.seq < args.antes_de_seq]
    mensagens = mensagens[-args.limite :]
    return "\n".join(f"[{m.seq}] {m.autor.value}: {m.texto}" for m in mensagens) or "Sem mensagens."


async def _disponiveis(sessao, usuario_id: UUID) -> set[UUID]:
    return set(
        (
            await sessao.scalars(
                select(Agente.id).where(
                    Agente.usuario_id == usuario_id,
                    Agente.apagado_em.is_(None),
                    Agente.fila_pausada.is_(False),
                )
            )
        ).all()
    )


async def canal_delegar(args: CanalDelegar, contexto: ContextoFerramenta) -> str:
    _, tarefa_id, revisao = _ids(contexto)
    async with fabrica_sessoes()() as sessao:
        armazem = ArmazemCanaisSQL(sessao)
        try:
            async with armazem.transacao_tarefa(tarefa_id):
                tarefa = await ServicoCanais(armazem).delegar(
                    tarefa_id,
                    revisao,
                    por_agente=contexto.agente_id,
                    para_agente=args.agente_id,
                    instrucao=args.instrucao,
                    disponiveis=await _disponiveis(sessao, contexto.usuario_id),
                )
            await sessao.commit()
        except Exception as erro:
            raise ErroFerramenta(str(erro)) from erro
    await _publicar_tarefa(contexto, tarefa)
    return f"Tarefa delegada: {tarefa.id}. Continue o que nao depende dela."


async def canal_transferir(args: CanalTransferir, contexto: ContextoFerramenta) -> str:
    _, tarefa_id, revisao = _ids(contexto)
    async with fabrica_sessoes()() as sessao:
        armazem = ArmazemCanaisSQL(sessao)
        try:
            async with armazem.transacao_tarefa(tarefa_id):
                tarefa = await ServicoCanais(armazem).transferir(
                    tarefa_id,
                    revisao,
                    por_agente=contexto.agente_id,
                    para_agente=args.agente_id,
                    nota=args.nota,
                    disponiveis=await _disponiveis(sessao, contexto.usuario_id),
                )
            await sessao.commit()
        except Exception as erro:
            raise ErroFerramenta(str(erro)) from erro
    await _publicar_tarefa(contexto, tarefa)
    return "Tarefa transferida. Encerre este turno."


async def canal_resultado(args: CanalResultado, contexto: ContextoFerramenta) -> str:
    from app.ferramentas.saidas_do_turno import recolher

    _, tarefa_id, revisao = _ids(contexto)
    # Imagens e arquivos que o bot produziu no turno chegam com o resultado (item 10, etapa 6).
    args = args.model_copy(
        update={
            "anexos": await recolher(contexto.usuario_id, contexto.agente_id, args.anexos or [])
        }
    )
    async with fabrica_sessoes()() as sessao:
        if args.anexos:
            from sqlalchemy import select

            from app.modelos.tabelas import Anexo

            encontrados = set(
                (
                    await sessao.scalars(
                        select(Anexo.id).where(
                            Anexo.usuario_id == contexto.usuario_id, Anexo.id.in_(args.anexos)
                        )
                    )
                ).all()
            )
            if encontrados != set(args.anexos):
                raise ErroFerramenta("Um dos anexos do resultado não pertence a esta conta.")
        armazem = ArmazemCanaisSQL(sessao)
        try:
            async with armazem.transacao_tarefa(tarefa_id):
                mudancas = await ServicoCanais(armazem).registrar_resultado(
                    tarefa_id,
                    revisao,
                    por_agente=contexto.agente_id,
                    texto=args.texto,
                    anexos=args.anexos,
                )
            await sessao.commit()
        except Exception as erro:
            raise ErroFerramenta(str(erro)) from erro
    redis = ambiente.redis_dos_eventos()
    for mensagem in mudancas.mensagens:
        await publicar_evento_equipe(
            redis,
            MensagemCanalEvento(
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
            ),
            contexto.usuario_id,
        )
    for tarefa in mudancas.tarefas:
        await _publicar_tarefa(contexto, tarefa)
    return "Resultado entregue ao canal."
