"""Jobs da cadeia (especificação §6, tabela "Os jobs", e §6.1, "Como uma etapa roda").

Todo job recebe o ``ctx`` do ARQ como primeiro argumento. Todo job começa
pegando o trabalho com ``UPDATE ... WHERE status = ... RETURNING`` (sem
trabalho em dobro) e termina chamando ``avancar_cadeia`` quando muda o
estado da cadeia.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage
from sqlalchemy import select

from app.agentes.aparencia import aparencia_do_especialista
from app.eventos.streams import publicar_evento
from app.eventos.tipos import (
    AgenteCriado,
    CadeiaAtualizada,
    CadeiaCriada,
    EntregaEvento,
    EtapaAtualizada,
    MensagemDelta,
    MensagemFim,
    MensagemInicio,
)
from app.eventos.tipos import (
    EtapaPlano as EtapaPlanoEvento,
)
from app.ferramentas.veredito import Veredito
from app.llm.falso import criar_modelo_falso, modelo_falso_ativo, respostas_prontas
from app.modelos.enumeracoes import (
    AutorMensagem,
    Nivel,
    StatusCadeia,
    StatusEtapa,
    TipoAgente,
    TipoEntrega,
)
from app.modelos.tabelas import Agente, Cadeia, Entrega, Etapa, Mensagem
from app.orquestrador.cadeia import EtapaResumo, decidir_avanco, pegar_etapa
from app.orquestrador.planejador import Plano, titulo_da_etapa, validar_plano
from workers.fila import enfileirar


def _uuid(valor: str) -> UUID:
    return UUID(valor)


async def _publicar(ctx: dict[str, Any], cadeia: Cadeia, evento: Any) -> None:
    await publicar_evento(ctx["redis_eventos"], evento, cadeia.conversa_id, cadeia.usuario_id)


def _custo(cadeia: Cadeia) -> float:
    return float(cadeia.custo_usd or Decimal(0))


def _conteudo_texto(resposta: Any) -> str:
    conteudo = resposta.content
    return conteudo if isinstance(conteudo, str) else str(conteudo)


def _chamada_da_ferramenta(papel: str, nome: str) -> dict[str, Any]:
    for resposta in respostas_prontas(papel):
        for chamada in resposta.tool_calls:
            if chamada["name"] == nome:
                return dict(chamada["args"])
    raise RuntimeError(f"o modelo falso de {papel} nao chamou {nome}")


async def planejar_cadeia(ctx: dict[str, Any], cadeia_id: str) -> None:
    """Chama o planejador (N3), grava o plano, cria as etapas e um especialista
    por papel; emite ``agente.criado`` e ``cadeia.criada``. Quem põe na fila: a API."""
    if not modelo_falso_ativo():
        raise RuntimeError("o caminho de modelo real depende da montagem do agente da Fase B")
    fabrica = ctx["sessoes"]
    async with fabrica() as sessao:
        cadeia = await sessao.get(Cadeia, _uuid(cadeia_id), with_for_update=True)
        if cadeia is None or cadeia.status != StatusCadeia.PLANEJANDO:
            return
        resposta = await criar_modelo_falso("planejador").ainvoke([HumanMessage("planeje")])
        plano = Plano.model_validate_json(_conteudo_texto(resposta))
        validar_plano(plano, tem_modelo_de_imagem=False)
        nomes = set((await sessao.scalars(select(Agente.nome))).all())
        cores = set((await sessao.scalars(select(Agente.cor))).all())
        eventos_agentes: list[AgenteCriado] = []
        eventos_etapas: list[EtapaPlanoEvento] = []
        for item in plano.etapas:
            aparencia = aparencia_do_especialista(item.especialista, nomes, cores)
            agente = Agente(
                usuario_id=cadeia.usuario_id,
                tipo=TipoAgente.ESPECIALISTA,
                nome=aparencia.nome,
                funcao=aparencia.funcao,
                papel=item.especialista,
                cor=aparencia.cor,
                movimento=aparencia.movimento,
                nivel_padrao=item.nivel.value,
                ferramentas=[],
                cadeia_id=cadeia.id,
            )
            sessao.add(agente)
            await sessao.flush()
            etapa = Etapa(
                cadeia_id=cadeia.id,
                ordem=item.ordem,
                depende_de=item.depende_de,
                especialista=item.especialista,
                agente_id=agente.id,
                titulo=titulo_da_etapa(item),
                nivel=item.nivel.value,
                tarefa=item.tarefa,
                status=StatusEtapa.PENDENTE,
            )
            sessao.add(etapa)
            await sessao.flush()
            nomes.add(aparencia.nome)
            cores.add(aparencia.cor)
            eventos_agentes.append(
                AgenteCriado(
                    agente_id=agente.id,
                    tipo=agente.tipo,
                    nome=agente.nome,
                    funcao=agente.funcao,
                    cor=agente.cor,
                    movimento=agente.movimento,
                )
            )
            eventos_etapas.append(
                EtapaPlanoEvento(
                    etapa_id=etapa.id,
                    ordem=etapa.ordem,
                    especialista=etapa.especialista,
                    agente_id=agente.id,
                    titulo=etapa.titulo,
                    nivel=Nivel(etapa.nivel),
                    depende_de=list(etapa.depende_de),
                )
            )
        cadeia.plano = plano.model_dump(mode="json")
        cadeia.status = StatusCadeia.EXECUTANDO
        await sessao.commit()
        for evento in eventos_agentes:
            await _publicar(ctx, cadeia, evento)
        await _publicar(
            ctx,
            cadeia,
            CadeiaCriada(cadeia_id=cadeia.id, versao=cadeia.versao, etapas=eventos_etapas),
        )
        await _publicar(
            ctx,
            cadeia,
            CadeiaAtualizada(
                cadeia_id=cadeia.id,
                status=cadeia.status,
                tokens_usados=cadeia.tokens_usados,
                custo_usd=_custo(cadeia),
            ),
        )
    await enfileirar("avancar_cadeia", cadeia_id=cadeia_id)


async def avancar_cadeia(ctx: dict[str, Any], cadeia_id: str) -> None:
    """Enfileira as etapas que já podem rodar (até 3 em paralelo) ou manda para
    verificação. Quem põe na fila: todo job que termina."""
    fabrica = ctx["sessoes"]
    async with fabrica() as sessao:
        cadeia = await sessao.get(Cadeia, _uuid(cadeia_id))
        if cadeia is None or cadeia.status not in {
            StatusCadeia.EXECUTANDO,
            StatusCadeia.VERIFICANDO,
        }:
            return
        etapas = list(
            (await sessao.scalars(select(Etapa).where(Etapa.cadeia_id == cadeia.id))).all()
        )
        resumos = [
            EtapaResumo(
                e.id,
                e.ordem,
                tuple(e.depende_de),
                e.status,
                e.especialista,
                e.tentativa,
            )
            for e in etapas
        ]
        decisao = decidir_avanco(resumos, passos_feitos=cadeia.passos)
        if decisao.acao == "executar":
            ids = [str(e.etapa_id) for e in decisao.etapas]
        elif decisao.acao == "verificar":
            ids = []
        elif decisao.acao in {"falhar", "limite"}:
            cadeia.status = StatusCadeia.FALHOU
            await sessao.commit()
            await _publicar(
                ctx,
                cadeia,
                CadeiaAtualizada(
                    cadeia_id=cadeia.id,
                    status=cadeia.status,
                    tokens_usados=cadeia.tokens_usados,
                    custo_usd=_custo(cadeia),
                ),
            )
            return
        else:
            return
    if decisao.acao == "verificar":
        await enfileirar("verificar_cadeia", cadeia_id=cadeia_id)
    else:
        for id_etapa in ids:
            await enfileirar("executar_etapa", etapa_id=id_etapa)


async def executar_etapa(ctx: dict[str, Any], etapa_id: str, resposta: Any | None = None) -> None:
    """Roda o especialista até ``entregar`` (ou retoma depois de uma pergunta ou
    aprovação, com ``resposta``). Prazo de 5 minutos. Quem põe na fila:
    ``avancar_cadeia`` e a API (retomada)."""
    del resposta
    if not modelo_falso_ativo():
        raise RuntimeError("o caminho real depende de Molde e Elo")
    fabrica = ctx["sessoes"]
    async with fabrica() as sessao:
        if not await pegar_etapa(sessao, _uuid(etapa_id)):
            await sessao.rollback()
            return
        etapa = await sessao.get(Etapa, _uuid(etapa_id))
        assert etapa is not None
        cadeia = await sessao.get(Cadeia, etapa.cadeia_id, with_for_update=True)
        assert cadeia is not None and etapa.agente_id is not None
        await sessao.commit()
        await _publicar(
            ctx,
            cadeia,
            EtapaAtualizada(
                etapa_id=etapa.id,
                status=StatusEtapa.EXECUTANDO,
                progresso=10,
                modelo="falso/" + etapa.especialista,
                tokens=0,
                custo_usd=0,
            ),
        )
        args = _chamada_da_ferramenta(etapa.especialista, "entregar")
        entrega = Entrega(
            usuario_id=cadeia.usuario_id,
            conversa_id=cadeia.conversa_id,
            cadeia_id=cadeia.id,
            etapa_id=etapa.id,
            agente_id=etapa.agente_id,
            versao=cadeia.versao,
            tipo=TipoEntrega(args["tipo"]),
            titulo=args["titulo"],
            resumo=args["resumo"],
            conteudo=args["conteudo"],
        )
        sessao.add(entrega)
        etapa.saida = args
        etapa.status = StatusEtapa.CONCLUIDA
        cadeia.passos += 1
        await sessao.commit()
        await _publicar(
            ctx,
            cadeia,
            EntregaEvento(
                entrega_id=entrega.id,
                agente_id=etapa.agente_id,
                versao=entrega.versao,
                tipo=entrega.tipo,
                titulo=entrega.titulo,
                resumo=entrega.resumo,
            ),
        )
        await _publicar(
            ctx,
            cadeia,
            EtapaAtualizada(
                etapa_id=etapa.id,
                status=etapa.status,
                progresso=100,
                modelo="falso/" + etapa.especialista,
                tokens=etapa.tokens,
                custo_usd=float(etapa.custo_usd or 0),
            ),
        )
    await enfileirar("avancar_cadeia", cadeia_id=str(cadeia.id))


async def verificar_cadeia(ctx: dict[str, Any], cadeia_id: str) -> None:
    """Roda o Verificador sobre o resultado e aplica a regra de reprovação.
    Quem põe na fila: ``avancar_cadeia``, quando todas as etapas terminam."""
    if not modelo_falso_ativo():
        raise RuntimeError("o caminho real depende da montagem do Verificador")
    fabrica = ctx["sessoes"]
    async with fabrica() as sessao:
        cadeia = await sessao.get(Cadeia, _uuid(cadeia_id), with_for_update=True)
        if cadeia is None or cadeia.status != StatusCadeia.EXECUTANDO:
            return
        verificador = await sessao.scalar(
            select(Etapa).where(
                Etapa.cadeia_id == cadeia.id,
                Etapa.especialista == "verificador",
                Etapa.status == StatusEtapa.PENDENTE,
            )
        )
        if verificador is None:
            raise RuntimeError("cadeia sem etapa de verificacao pendente")
        cadeia.status = StatusCadeia.VERIFICANDO
        verificador.status = StatusEtapa.EXECUTANDO
        await sessao.commit()
        await _publicar(
            ctx,
            cadeia,
            CadeiaAtualizada(
                cadeia_id=cadeia.id,
                status=cadeia.status,
                tokens_usados=cadeia.tokens_usados,
                custo_usd=_custo(cadeia),
            ),
        )
        args = _chamada_da_ferramenta("verificador", "veredito")
        veredito = Veredito.model_validate(args)
        cadeia.rodada += 1
        verificador.saida = veredito.model_dump(mode="json")
        verificador.status = StatusEtapa.CONCLUIDA if veredito.aprovado else StatusEtapa.FALHOU
        await sessao.commit()
        await _publicar(
            ctx,
            cadeia,
            EtapaAtualizada(
                etapa_id=verificador.id,
                status=verificador.status,
                progresso=100,
                modelo="falso/verificador",
                tokens=0,
                custo_usd=0,
            ),
        )
    if veredito.aprovado:
        await enfileirar("entregar_resultado", cadeia_id=cadeia_id)
    else:
        async with fabrica() as sessao:
            cadeia = await sessao.get(Cadeia, _uuid(cadeia_id), with_for_update=True)
            assert cadeia is not None
            cadeia.status = StatusCadeia.FALHOU
            await sessao.commit()


async def entregar_resultado(ctx: dict[str, Any], cadeia_id: str) -> None:
    """A Sora escreve a resposta final com a voz dela; a cadeia fica ``concluida``.
    Quem põe na fila: ``verificar_cadeia``, quando aprova."""
    fabrica = ctx["sessoes"]
    async with fabrica() as sessao:
        cadeia = await sessao.get(Cadeia, _uuid(cadeia_id), with_for_update=True)
        if cadeia is None or cadeia.status != StatusCadeia.VERIFICANDO:
            return
        mensagem = Mensagem(
            conversa_id=cadeia.conversa_id,
            autor=AutorMensagem.SORA,
            conteudo="Pronto! A equipe concluiu o trabalho. Revise as entregas antes de publicar.",
            anexos=[],
            visivel=True,
        )
        sessao.add(mensagem)
        cadeia.status = StatusCadeia.CONCLUIDA
        await sessao.commit()
        await _publicar(
            ctx,
            cadeia,
            MensagemInicio(mensagem_id=mensagem.id, autor=AutorMensagem.SORA),
        )
        await _publicar(
            ctx, cadeia, MensagemDelta(mensagem_id=mensagem.id, texto=mensagem.conteudo)
        )
        await _publicar(ctx, cadeia, MensagemFim(mensagem_id=mensagem.id, anexos=[]))
        await _publicar(
            ctx,
            cadeia,
            CadeiaAtualizada(
                cadeia_id=cadeia.id,
                status=cadeia.status,
                tokens_usados=cadeia.tokens_usados,
                custo_usd=_custo(cadeia),
            ),
        )


async def ajustar(
    ctx: dict[str, Any], conversa_id: str, texto: str, agente_id: str | None = None
) -> None:
    """Cria a cadeia ``versao + 1`` só com o especialista certo e o Verificador.
    Quem põe na fila: a API, em ``POST /ajuste``."""
    raise NotImplementedError
