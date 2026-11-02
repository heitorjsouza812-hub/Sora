"""Jobs da cadeia (especificação §6, tabela "Os jobs", e §6.1, "Como uma etapa roda").

Todo job recebe o ``ctx`` do ARQ como primeiro argumento. Todo job começa
pegando o trabalho com ``UPDATE ... WHERE status = ... RETURNING`` (sem
trabalho em dobro) e termina chamando ``avancar_cadeia`` quando muda o
estado da cadeia.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage
from sqlalchemy import select, update

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
from app.llm.falso import modelo_falso_ativo, respostas_prontas
from app.modelos.enumeracoes import (
    AutorMensagem,
    Nivel,
    StatusCadeia,
    StatusEtapa,
    TipoAgente,
    TipoEntrega,
)
from app.modelos.tabelas import Agente, Cadeia, Conversa, Entrega, Etapa, Mensagem
from app.orquestrador.cadeia import EtapaResumo, decidir_avanco, pegar_etapa, retomar_etapa
from app.orquestrador.planejador import Plano, titulo_da_etapa, validar_plano
from workers.fila import enfileirar
from workers.travados import batimento

registro = logging.getLogger(__name__)


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


def _json_do_texto(texto: str) -> str:
    """O trecho entre a primeira ``{`` e a ultima ``}`` (modelos costumam cercar o JSON)."""
    inicio, fim = texto.find("{"), texto.rfind("}")
    return texto[inicio : fim + 1] if inicio >= 0 and fim > inicio else texto


async def _tem_modelo_de_imagem(sessao: Any, usuario_id: UUID) -> bool:
    """O Designer só entra no plano se o usuário conectou um modelo de imagem (§5)."""
    if modelo_falso_ativo():
        return False
    from app.seletor.repositorio import contexto_do_usuario
    from app.seletor.seletor import tem_modelo_de_imagem

    return tem_modelo_de_imagem(await contexto_do_usuario(sessao, usuario_id))


async def _obter_plano(ctx: dict[str, Any], sessao: Any, cadeia: Cadeia) -> Plano:
    """Chama o planejador (N3) pelo seletor; tenta os modelos em ordem ate um plano valido."""
    from app.agentes.montagem import FERRAMENTAS_POR_PAPEL
    from app.agentes.prompts import carregar_prompt, preencher
    from app.orquestrador.modelos import modelos_do_papel

    pedido = await sessao.scalar(select(Mensagem.conteudo).where(Mensagem.id == cadeia.pedido_id))
    com_imagem = await _tem_modelo_de_imagem(sessao, cadeia.usuario_id)
    especialistas = "; ".join(
        f"{papel}: {', '.join(ferramentas)}"
        for papel, ferramentas in FERRAMENTAS_POR_PAPEL.items()
        if papel not in {"sora", "individual"} and (com_imagem or papel != "designer")
    )
    prompt = preencher(
        carregar_prompt("planejador"),
        pedido=pedido or "",
        resumo_da_conversa="nenhum",
        memorias_relevantes="nenhuma",
        especialistas_e_ferramentas=especialistas,
    )
    modelos = await modelos_do_papel(
        sessao, cadeia.usuario_id, "planejador", dificuldade=3, precisa=()
    )
    ultimo: Exception | None = None
    for modelo in modelos:
        try:
            resposta = await modelo.ainvoke([HumanMessage(prompt)])
            plano = Plano.model_validate_json(_json_do_texto(_conteudo_texto(resposta)))
            validar_plano(plano, tem_modelo_de_imagem=com_imagem)
            return plano
        except Exception as erro:
            ultimo = erro
    raise RuntimeError(f"o planejador nao devolveu um plano valido: {ultimo}")


async def _falhar_cadeia(ctx: dict[str, Any], sessao: Any, cadeia: Cadeia) -> None:
    """Cadeia ``falhou`` + evento: o usuário nunca fica olhando uma cadeia presa."""
    cadeia_id = cadeia.id
    await sessao.rollback()
    cadeia = await sessao.get(Cadeia, cadeia_id, with_for_update=True)
    if cadeia is None:
        return
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


async def planejar_cadeia(ctx: dict[str, Any], cadeia_id: str) -> None:
    """Chama o planejador (N3), grava o plano, cria as etapas e um especialista
    por papel; emite ``agente.criado`` e ``cadeia.criada``. Quem põe na fila: a API.
    Qualquer erro vira ``falhou`` com evento (a cadeia nunca fica presa em ``planejando``)."""
    fabrica = ctx["sessoes"]
    async with fabrica() as sessao:
        cadeia = await sessao.get(Cadeia, _uuid(cadeia_id), with_for_update=True)
        if cadeia is None or cadeia.status != StatusCadeia.PLANEJANDO:
            return
        try:
            eventos = await _criar_equipe(ctx, sessao, cadeia)
        except Exception:
            await _falhar_cadeia(ctx, sessao, cadeia)
            return
        eventos_agentes, eventos_etapas = eventos
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


async def _criar_equipe(
    ctx: dict[str, Any], sessao: Any, cadeia: Cadeia
) -> tuple[list[AgenteCriado], list[EtapaPlanoEvento]]:
    """Plano + um especialista por etapa, commitados juntos. Nomes são por usuário; cores,
    por usuário e conversa (quando a paleta acaba, reutiliza a menos usada)."""
    plano = await _obter_plano(ctx, sessao, cadeia)
    nomes = set(
        (
            await sessao.scalars(select(Agente.nome).where(Agente.usuario_id == cadeia.usuario_id))
        ).all()
    )
    cores = list(
        (
            await sessao.scalars(
                select(Agente.cor)
                .join(Cadeia, Cadeia.id == Agente.cadeia_id)
                .where(
                    Agente.usuario_id == cadeia.usuario_id,
                    Cadeia.conversa_id == cadeia.conversa_id,
                )
            )
        ).all()
    )
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
        cores.append(aparencia.cor)
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
    if modelo_falso_ativo():
        # Gatilho de teste (só no modelo falso, barrado em produção): `[orcamento]` no pedido
        # baixa o teto da cadeia para a primeira chamada estourar (cartão Continuar/Parar).
        pedido = await sessao.scalar(
            select(Mensagem.conteudo).where(Mensagem.id == cadeia.pedido_id)
        )
        if "[orcamento]" in (pedido or ""):
            cadeia.orcamento_tokens = 100
    await sessao.commit()
    return eventos_agentes, eventos_etapas


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


async def _modelos_da_etapa(
    ctx: dict[str, Any], sessao: Any, usuario_id: UUID, papel: str, nivel: str = "N2"
) -> list[Any]:
    """Modelos na ordem do seletor. ``ctx["modelos_da_etapa"]`` (teste) tem prioridade."""
    from app.orquestrador.modelos import modelos_do_papel

    fabrica_de_modelos = ctx.get("modelos_da_etapa")
    if fabrica_de_modelos is not None:
        return list(fabrica_de_modelos(papel))
    dificuldade = int(nivel[1]) if len(nivel) == 2 and nivel[1].isdigit() else 2
    return await modelos_do_papel(sessao, usuario_id, papel, dificuldade=dificuldade)


def valor_da_retomada(resposta: Any) -> Any:
    """A API manda ``{"pergunta_id", "valor"}`` ou ``{"aprovacao_id", "decisao"}``; as
    ferramentas ``perguntar`` e ``criar_agente`` esperam so o valor/decisao no ``resume``."""
    if isinstance(resposta, dict):
        if "valor" in resposta:
            return resposta["valor"]
        if "decisao" in resposta:
            return resposta["decisao"]
    return resposta


def _estado_da_pausa(valor: Any) -> StatusEtapa:
    tipo = valor.get("tipo") if isinstance(valor, dict) else None
    if tipo == "pergunta":
        return StatusEtapa.AGUARDANDO_USUARIO
    if tipo == "aprovacao":
        return StatusEtapa.AGUARDANDO_APROVACAO
    raise RuntimeError(f"interrupcao desconhecida: {valor!r}")


def _evento_etapa(etapa: Etapa, progresso: int) -> EtapaAtualizada:
    return EtapaAtualizada(
        etapa_id=etapa.id,
        status=etapa.status,
        progresso=progresso,
        modelo=etapa.modelo or "",
        tokens=etapa.tokens,
        custo_usd=float(etapa.custo_usd or 0),
    )


async def _valores_do_prompt(sessao: Any, etapa: Etapa, cadeia: Cadeia) -> dict[str, Any]:
    """Preenchimento do prompt do especialista: plano, tarefa e entregas das etapas anteriores."""
    agente = await sessao.get(Agente, etapa.agente_id)
    plano = cadeia.plano or {}
    pronto = next(
        (
            e.get("pronto_quando", "")
            for e in plano.get("etapas", [])
            if e.get("ordem") == etapa.ordem
        ),
        "",
    )
    anteriores = (
        await sessao.scalars(
            select(Entrega)
            .join(Etapa, Etapa.id == Entrega.etapa_id)
            .where(Etapa.cadeia_id == cadeia.id, Etapa.ordem.in_(etapa.depende_de or []))
            .order_by(Etapa.ordem)
        )
    ).all()
    return {
        "nome": agente.nome if agente else etapa.especialista,
        "papel": etapa.especialista,
        "objetivo": plano.get("objetivo", ""),
        "tarefa": etapa.tarefa,
        "pronto_quando": pronto,
        "resultados_anteriores": "\n".join(f"- {e.titulo}: {e.resumo}" for e in anteriores)
        or "nenhum",
    }


def dependencias_da_etapa(
    ctx: dict[str, Any] | None = None,
    *,
    cadeia: Cadeia | None = None,
    usuario_id: UUID | None = None,
    conversa_id: UUID | None = None,
    etapa: Etapa | None = None,
) -> Any:
    """Portas que o worker entrega ao agente: cancelamento, orçamento, passos do painel
    Trabalho, saída grande e as correções da Sora (``mensagem_especialista``).
    Sem ``ctx`` (testes unitários) só liga o correio."""
    from app.agentes.montagem import DependenciasAgente
    from app.ferramentas import ambiente

    if ctx is None or ctx.get("redis_eventos") is None:
        return DependenciasAgente(ler_mensagens_pendentes=ambiente.ler_mensagens_pendentes)
    from workers.portas import construir_dependencias

    return construir_dependencias(
        ctx,
        usuario_id=cadeia.usuario_id if cadeia else usuario_id,
        conversa_id=cadeia.conversa_id if cadeia else conversa_id,
        cadeia_id=cadeia.id if cadeia else None,
        orcamento_tokens=cadeia.orcamento_tokens if cadeia else None,
        etapa_id=etapa.id if etapa else None,
        agente_id=etapa.agente_id if etapa else None,
    )


ERRO_SEGURO_DA_ETAPA = (
    "A etapa não terminou porque o modelo de IA não respondeu. Confira o provedor em "
    "Configurações → Modelos de IA e peça de novo."
)
ERRO_SEGURO_DO_VERIFICADOR = (
    "Não consegui verificar o resultado porque o modelo de IA não respondeu. Peça de novo."
)


def _foi_cancelamento(erro: BaseException | None) -> bool:
    from app.agentes.middleware.cancelamento import CadeiaCancelada

    visto: set[int] = set()
    while erro is not None and id(erro) not in visto:
        if isinstance(erro, CadeiaCancelada):
            return True
        visto.add(id(erro))
        erro = erro.__cause__ or erro.__context__
    return False


def _estourou_orcamento(erro: BaseException | None) -> bool:
    from app.agentes.middleware.orcamento import OrcamentoEstourado

    visto: set[int] = set()
    while erro is not None and id(erro) not in visto:
        if isinstance(erro, OrcamentoEstourado):
            return True
        visto.add(id(erro))
        erro = erro.__cause__ or erro.__context__
    return False


PERGUNTA_DO_ORCAMENTO = (
    "O orçamento de tokens desta equipe acabou antes de terminar o trabalho. Posso continuar "
    "com mais orçamento?"
)


async def _pausar_por_orcamento(
    ctx: dict[str, Any], sessao: Any, cadeia: Cadeia, etapa: Etapa
) -> None:
    """§6 "Orçamento": passou do teto -> etapa e cadeia em ``aguardando_usuario`` e a Sora
    pergunta se pode continuar (cartão com "Continuar" e "Parar")."""
    from app.eventos.tipos import OpcaoPergunta, PerguntaEvento
    from app.modelos.tabelas import Pergunta

    opcoes = [{"rotulo": "Continuar", "valor": "continuar"}, {"rotulo": "Parar", "valor": "parar"}]
    pergunta = Pergunta(
        conversa_id=cadeia.conversa_id,
        cadeia_id=cadeia.id,
        texto=PERGUNTA_DO_ORCAMENTO,
        opcoes=opcoes,
        resposta_livre=False,
    )
    sessao.add(pergunta)
    await sessao.flush()
    etapa.status = StatusEtapa.AGUARDANDO_USUARIO
    etapa.saida = {"pergunta_id": str(pergunta.id), "orcamento": True}
    cadeia.status = StatusCadeia.AGUARDANDO_USUARIO
    await sessao.commit()
    await _publicar(
        ctx,
        cadeia,
        PerguntaEvento(
            pergunta_id=pergunta.id,
            texto=pergunta.texto,
            opcoes=[OpcaoPergunta(**o) for o in opcoes],
            resposta_livre=False,
        ),
    )
    await _publicar(ctx, cadeia, _evento_etapa(etapa, 50))
    await _publicar(ctx, cadeia, _evento_cadeia(cadeia))


async def _resposta_do_orcamento(ctx: dict[str, Any], etapa_id: str, valor: Any) -> bool:
    """Se a etapa parou pelo orçamento, trata a resposta e devolve ``True``.

    ``continuar`` soma ao teto o mesmo valor do orçamento original e põe a etapa de volta na
    fila (o agente recomeça do checkpoint); ``parar`` falha a etapa e, por ela, a cadeia."""
    async with ctx["sessoes"]() as sessao:
        etapa = await sessao.get(Etapa, _uuid(etapa_id))
        if (
            etapa is None
            or etapa.status != StatusEtapa.AGUARDANDO_USUARIO
            or not (etapa.saida or {}).get("orcamento")
        ):
            return False
        cadeia = await sessao.get(Cadeia, etapa.cadeia_id, with_for_update=True)
        if cadeia is None:
            return False
        continuar = str(valor) == "continuar"
        ganhou = await sessao.scalar(
            update(Etapa)
            .where(Etapa.id == etapa.id, Etapa.status == StatusEtapa.AGUARDANDO_USUARIO)
            .values(
                status=StatusEtapa.PENDENTE if continuar else StatusEtapa.FALHOU,
                erro=None if continuar else "Parado a pedido do usuário: orçamento de tokens.",
            )
            .returning(Etapa.id)
        )
        if ganhou is None:
            await sessao.rollback()
            return True  # resposta repetida: outra já decidiu
        if continuar:
            cadeia.orcamento_tokens += max(cadeia.orcamento_tokens, 50_000)
        if cadeia.status == StatusCadeia.AGUARDANDO_USUARIO:
            cadeia.status = StatusCadeia.EXECUTANDO
        await sessao.commit()
        await sessao.refresh(etapa)
        await _publicar(ctx, cadeia, _evento_etapa(etapa, 50 if continuar else 100))
        await _publicar(ctx, cadeia, _evento_cadeia(cadeia))
    if continuar:
        await enfileirar("executar_etapa", etapa_id=etapa_id)
    else:
        await enfileirar("avancar_cadeia", cadeia_id=str(cadeia.id))
    return True


async def _contar_passo(sessao: Any, cadeia_id: UUID) -> None:
    """``passos = passos + 1`` no banco: etapas em paralelo não perdem incrementos."""
    await sessao.execute(
        update(Cadeia).where(Cadeia.id == cadeia_id).values(passos=Cadeia.passos + 1)
    )


async def _retomar_quando_pausar(sessao: Any, etapa_id: UUID) -> bool:
    """``retomar_etapa`` com uma pequena espera: o cartão (pergunta ou aprovação) aparece para o
    usuário um instante antes de o worker gravar a pausa da etapa. Se a resposta chegar nesse
    intervalo a etapa ainda está `executando`; esperar a pausa evita perder a resposta."""
    for _ in range(40):
        if await retomar_etapa(sessao, etapa_id):
            return True
        await sessao.rollback()
        status = await sessao.scalar(select(Etapa.status).where(Etapa.id == etapa_id))
        await sessao.rollback()
        if status != StatusEtapa.EXECUTANDO:
            return False  # resposta repetida, etapa cancelada ou já retomada
        await asyncio.sleep(0.25)
    return False


async def _executar_com_agente(ctx: dict[str, Any], etapa_id: str, resposta: Any | None) -> None:
    """Roda a etapa com o agente de verdade (ferramentas reais). ``entregar`` ja grava a
    entrega e emite o evento: aqui so se conclui a etapa. ``__interrupt__`` (``perguntar`` e
    ``criar_agente``) pausa a etapa; a retomada chega com ``resposta``."""
    from app.agentes import ContextoAgente, montar_e_rodar_agente

    if isinstance(resposta, dict) and resposta.get("tipo") == "mensagem_usuario":
        # Mensagem direta do usuario a um especialista com etapa ativa: entra pelo correio
        # (o middleware injeta antes da proxima chamada); etapa pausada segue pausada.
        from app.ferramentas.ambiente import guardar_mensagem

        await guardar_mensagem(_uuid(etapa_id), str(resposta.get("texto", "")))
        return
    resposta = valor_da_retomada(resposta)
    retomada = resposta is not None
    if retomada and await _resposta_do_orcamento(ctx, etapa_id, resposta):
        return
    async with ctx["sessoes"]() as sessao:
        pegou = (
            await _retomar_quando_pausar(sessao, _uuid(etapa_id))
            if retomada
            else await pegar_etapa(sessao, _uuid(etapa_id))
        )
        if not pegou:
            await sessao.rollback()
            return
        etapa = await sessao.get(Etapa, _uuid(etapa_id))
        if etapa is None:
            await sessao.rollback()
            return
        cadeia = await sessao.get(Cadeia, etapa.cadeia_id, with_for_update=True)
        assert cadeia is not None
        if etapa.agente_id is None:
            etapa.status = StatusEtapa.FALHOU
            etapa.erro = "a etapa não tem agente"
            await sessao.commit()
            await _publicar(ctx, cadeia, _evento_etapa(etapa, 100))
            await enfileirar("avancar_cadeia", cadeia_id=str(cadeia.id))
            return
        if cadeia.status == StatusCadeia.AGUARDANDO_USUARIO:
            cadeia.status = StatusCadeia.EXECUTANDO
        await sessao.commit()
        await _publicar(ctx, cadeia, _evento_etapa(etapa, 10))
        contexto = ContextoAgente(
            usuario_id=cadeia.usuario_id,
            agente_id=etapa.agente_id,
            conversa_id=cadeia.conversa_id,
            papel=etapa.especialista,
            cadeia_id=cadeia.id,
            etapa_id=etapa.id,
            valores_do_prompt=await _valores_do_prompt(sessao, etapa, cadeia),
            ferramentas_extras=list(ctx.get("ferramentas_extras", ["perguntar", "criar_agente"])),
            dependencias=dependencias_da_etapa(ctx, cadeia=cadeia, etapa=etapa),
        )
        try:
            async with batimento(ctx["redis_eventos"], etapa.id):
                resultado = await montar_e_rodar_agente(
                    contexto=contexto,
                    modelos=await _modelos_da_etapa(
                        ctx, sessao, cadeia.usuario_id, etapa.especialista, etapa.nivel
                    ),
                    checkpointer=ctx["checkpointer"],
                    entrada=None if retomada else {"messages": [HumanMessage(etapa.tarefa)]},
                    resposta=resposta,
                )
        except Exception as erro:
            if _estourou_orcamento(erro):
                await _pausar_por_orcamento(ctx, sessao, cadeia, etapa)
                return
            await sessao.refresh(cadeia)
            if _foi_cancelamento(erro) or cadeia.status == StatusCadeia.CANCELADA:
                # cancelar no meio: a etapa fica `cancelada`, não `falhou`
                etapa.status = StatusEtapa.CANCELADA
                etapa.erro = None
                await sessao.commit()
                await _publicar(ctx, cadeia, _evento_etapa(etapa, 100))
                return
            # o texto cru do provedor (URL, trecho de chave) vai só para o log, nunca para a API
            registro.warning(
                "etapa %s falhou (%s): %s", etapa.id, type(erro).__name__, str(erro)[:300]
            )
            from app.llm.limite import MENSAGEM_LIMITE, limite_do_provedor

            etapa.status = StatusEtapa.FALHOU
            etapa.erro = MENSAGEM_LIMITE if limite_do_provedor(erro) else ERRO_SEGURO_DA_ETAPA
            await sessao.commit()
            await _publicar(ctx, cadeia, _evento_etapa(etapa, 100))
            await enfileirar("avancar_cadeia", cadeia_id=str(cadeia.id))
            return
        interrupcoes = resultado.get("__interrupt__")
        if interrupcoes:
            valor = getattr(interrupcoes[0], "value", interrupcoes[0])
            etapa.status = _estado_da_pausa(valor)
            if isinstance(valor, dict) and valor.get("pergunta_id"):
                # Liga a pergunta a esta etapa: com etapas em paralelo, a API acorda a certa.
                etapa.saida = {"pergunta_id": str(valor["pergunta_id"])}
            if etapa.status == StatusEtapa.AGUARDANDO_USUARIO:
                cadeia.status = StatusCadeia.AGUARDANDO_USUARIO
            await sessao.commit()
            await _publicar(ctx, cadeia, _evento_etapa(etapa, 50))
            if cadeia.status == StatusCadeia.AGUARDANDO_USUARIO:
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
        entrega = await sessao.scalar(select(Entrega).where(Entrega.etapa_id == etapa.id))
        if entrega is None:
            etapa.status = StatusEtapa.FALHOU
            etapa.erro = "o agente terminou sem entregar"
        else:
            etapa.status = StatusEtapa.CONCLUIDA
            etapa.saida = {"entrega_id": str(entrega.id), "titulo": entrega.titulo}
            await _contar_passo(sessao, cadeia.id)
        await sessao.commit()
        await _publicar(ctx, cadeia, _evento_etapa(etapa, 100))
    await enfileirar("avancar_cadeia", cadeia_id=str(cadeia.id))


async def executar_etapa(ctx: dict[str, Any], etapa_id: str, resposta: Any | None = None) -> None:
    """Roda o especialista até ``entregar`` (ou retoma depois de uma pergunta ou
    aprovação, com ``resposta``). Prazo de 5 minutos. Quem põe na fila:
    ``avancar_cadeia`` e a API (retomada)."""
    if ctx.get("checkpointer") is not None:
        await _executar_com_agente(ctx, etapa_id, resposta)
        return
    if not modelo_falso_ativo():
        raise RuntimeError("o caminho real exige o checkpointer no ctx do worker")
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
        await _contar_passo(sessao, cadeia.id)
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


async def _rodar_verificador(
    ctx: dict[str, Any], sessao: Any, cadeia: Cadeia, verificador: Etapa
) -> Veredito:
    """Roda o Verificador como agente; a ferramenta ``veredito`` grava ``etapas.saida``."""
    from app.agentes import ContextoAgente, montar_e_rodar_agente

    pedido = await sessao.scalar(select(Mensagem.conteudo).where(Mensagem.id == cadeia.pedido_id))
    entregas = (
        await sessao.scalars(
            select(Entrega).where(Entrega.cadeia_id == cadeia.id).order_by(Entrega.criada_em)
        )
    ).all()
    requisitos = (cadeia.plano or {}).get("requisitos", [])
    contexto = ContextoAgente(
        usuario_id=cadeia.usuario_id,
        agente_id=verificador.agente_id,
        conversa_id=cadeia.conversa_id,
        papel="verificador",
        cadeia_id=cadeia.id,
        etapa_id=verificador.id,
        valores_do_prompt={
            "pedido": pedido or "",
            "requisitos": "\n".join(f"- {r}" for r in requisitos) or "nenhum",
            "resultados": "\n".join(
                f"- {e.titulo}: {e.resumo}\n  {str(e.conteudo)[:2000]}" for e in entregas
            )
            or "nenhum",
        },
        dependencias=dependencias_da_etapa(ctx, cadeia=cadeia, etapa=verificador),
    )
    async with batimento(ctx["redis_eventos"], verificador.id):
        await montar_e_rodar_agente(
            contexto=contexto,
            modelos=await _modelos_da_etapa(
                ctx, sessao, cadeia.usuario_id, "verificador", verificador.nivel
            ),
            checkpointer=ctx["checkpointer"],
            entrada={"messages": [HumanMessage(verificador.tarefa)]},
        )
    await sessao.refresh(verificador)
    bruto = (verificador.saida or {}).get("veredito")
    if bruto is None:
        raise RuntimeError("o Verificador terminou sem chamar veredito")
    return Veredito.model_validate(bruto)


def _evento_cadeia(cadeia: Cadeia) -> CadeiaAtualizada:
    return CadeiaAtualizada(
        cadeia_id=cadeia.id,
        status=cadeia.status,
        tokens_usados=cadeia.tokens_usados,
        custo_usd=_custo(cadeia),
    )


async def _concluir_verificacao_com_falha(
    ctx: dict[str, Any], sessao: Any, cadeia_id: UUID, verificador_id: UUID, erro: str
) -> None:
    """O Verificador quebrou: etapa e cadeia ``falhou``, com evento (nunca presas)."""
    await sessao.rollback()
    cadeia = await sessao.get(Cadeia, cadeia_id, with_for_update=True)
    verificador = await sessao.get(Etapa, verificador_id)
    if cadeia is None or verificador is None:
        return
    verificador.status = StatusEtapa.FALHOU
    registro.warning("verificador da cadeia %s falhou: %s", cadeia_id, erro[:300])
    verificador.erro = ERRO_SEGURO_DO_VERIFICADOR
    if cadeia.status not in {StatusCadeia.CANCELADA, StatusCadeia.CONCLUIDA}:
        cadeia.status = StatusCadeia.FALHOU
    await sessao.commit()
    await _publicar(ctx, cadeia, _evento_etapa(verificador, 100))
    await _publicar(ctx, cadeia, _evento_cadeia(cadeia))


async def _refazer_etapas_reprovadas(sessao: Any, cadeia: Cadeia) -> list[EtapaPlanoEvento]:
    """§6, "Reprovação": cada etapa de trabalho ganha uma nova tentativa um nível acima
    (N2 para N3), uma única vez, mais um novo Verificador. O Veredito não aponta etapas
    específicas, então a nova tentativa vale para todas as etapas de trabalho."""
    from app.orquestrador.verificador import subir_nivel

    todas = list((await sessao.scalars(select(Etapa).where(Etapa.cadeia_id == cadeia.id))).all())
    ultimas: dict[int, Etapa] = {}
    for etapa in todas:
        if etapa.ordem not in ultimas or etapa.tentativa > ultimas[etapa.ordem].tentativa:
            ultimas[etapa.ordem] = etapa
    novas: list[Etapa] = []
    for etapa in sorted(ultimas.values(), key=lambda e: e.ordem):
        nivel = etapa.nivel if etapa.especialista == "verificador" else subir_nivel(etapa.nivel)
        novas.append(
            Etapa(
                cadeia_id=cadeia.id,
                ordem=etapa.ordem,
                depende_de=list(etapa.depende_de),
                especialista=etapa.especialista,
                agente_id=etapa.agente_id,
                titulo=etapa.titulo,
                nivel=nivel,
                tarefa=etapa.tarefa,
                tentativa=etapa.tentativa + 1,
                status=StatusEtapa.PENDENTE,
            )
        )
    sessao.add_all(novas)
    await sessao.flush()
    return [
        EtapaPlanoEvento(
            etapa_id=e.id,
            ordem=e.ordem,
            especialista=e.especialista,
            agente_id=e.agente_id,
            titulo=e.titulo,
            nivel=Nivel(e.nivel),
            depende_de=list(e.depende_de),
        )
        for e in novas
    ]


async def verificar_cadeia(ctx: dict[str, Any], cadeia_id: str) -> None:
    """Roda o Verificador sobre o resultado e aplica a regra de reprovação (§6): na primeira
    reprovação as etapas ganham outra tentativa um nível acima; na segunda a cadeia falha.
    Quem põe na fila: ``avancar_cadeia``, quando todas as etapas terminam."""
    from app.orquestrador.verificador import decidir

    if ctx.get("checkpointer") is None and not modelo_falso_ativo():
        raise RuntimeError("o caminho real exige o checkpointer no ctx do worker")
    fabrica = ctx["sessoes"]
    async with fabrica() as sessao:
        cadeia = await sessao.get(Cadeia, _uuid(cadeia_id), with_for_update=True)
        if cadeia is None or cadeia.status != StatusCadeia.EXECUTANDO:
            return
        verificador = await sessao.scalar(
            select(Etapa)
            .where(
                Etapa.cadeia_id == cadeia.id,
                Etapa.especialista == "verificador",
                Etapa.status == StatusEtapa.PENDENTE,
            )
            .order_by(Etapa.tentativa.desc())
            .limit(1)
        )
        if verificador is None:
            raise RuntimeError("cadeia sem etapa de verificacao pendente")
        cadeia.status = StatusCadeia.VERIFICANDO
        verificador.status = StatusEtapa.EXECUTANDO
        verificador.iniciada_em = datetime.now(UTC)
        await sessao.commit()
        verificador_id = verificador.id
        await _publicar(ctx, cadeia, _evento_cadeia(cadeia))
        try:
            if ctx.get("checkpointer") is not None:
                veredito = await _rodar_verificador(ctx, sessao, cadeia, verificador)
            else:
                args = _chamada_da_ferramenta("verificador", "veredito")
                veredito = Veredito.model_validate(args)
                verificador.saida = {"veredito": veredito.model_dump(mode="json")}
        except Exception as erro:
            await _concluir_verificacao_com_falha(
                ctx, sessao, cadeia.id, verificador_id, f"{type(erro).__name__}: {erro}"
            )
            return
        cadeia.rodada += 1
        decisao = decidir(veredito, rodada=cadeia.rodada, max_rodadas=2)
        verificador.status = StatusEtapa.CONCLUIDA if decisao.concluir else StatusEtapa.FALHOU
        novas: list[EtapaPlanoEvento] = []
        if decisao.falhar:
            cadeia.status = StatusCadeia.FALHOU
        elif not decisao.concluir:
            novas = await _refazer_etapas_reprovadas(sessao, cadeia)
            cadeia.status = StatusCadeia.EXECUTANDO
        await sessao.commit()
        await _publicar(ctx, cadeia, _evento_etapa(verificador, 100))
        if novas:
            await _publicar(
                ctx, cadeia, CadeiaCriada(cadeia_id=cadeia.id, versao=cadeia.versao, etapas=novas)
            )
        if not decisao.concluir:
            await _publicar(ctx, cadeia, _evento_cadeia(cadeia))
    if decisao.concluir:
        await enfileirar("entregar_resultado", cadeia_id=cadeia_id)
    elif not decisao.falhar:
        await enfileirar("avancar_cadeia", cadeia_id=cadeia_id)


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
    Quem põe na fila: a API, em ``POST /ajuste``. Sem ``agente_id``, o especialista é o da
    última etapa de trabalho da versão anterior (a que produz o resultado final)."""
    async with ctx["sessoes"]() as sessao:
        # Trava a conversa: dois cliques seguidos geram v2 e v3, nunca duas v2.
        await sessao.scalar(
            select(Conversa.id).where(Conversa.id == _uuid(conversa_id)).with_for_update()
        )
        anterior = await sessao.scalar(
            select(Cadeia)
            .where(Cadeia.conversa_id == _uuid(conversa_id))
            .order_by(Cadeia.versao.desc())
            .limit(1)
        )
        if anterior is None:
            return
        etapas = list(
            (
                await sessao.scalars(
                    select(Etapa).where(Etapa.cadeia_id == anterior.id).order_by(Etapa.ordem)
                )
            ).all()
        )
        trabalho = [e for e in etapas if e.especialista != "verificador"]
        verificacao = next((e for e in etapas if e.especialista == "verificador"), None)
        if not trabalho or verificacao is None:
            return
        escolhida = next(
            (e for e in trabalho if agente_id and str(e.agente_id) == agente_id), trabalho[-1]
        )
        entrega = await sessao.scalar(select(Entrega).where(Entrega.etapa_id == escolhida.id))
        pedido = Mensagem(
            conversa_id=anterior.conversa_id,
            autor=AutorMensagem.USUARIO,
            conteudo=texto,
            anexos=[],
            visivel=True,
        )
        sessao.add(pedido)
        await sessao.flush()
        nova = Cadeia(
            usuario_id=anterior.usuario_id,
            conversa_id=anterior.conversa_id,
            pedido_id=pedido.id,
            status=StatusCadeia.EXECUTANDO,
            versao=anterior.versao + 1,
            orcamento_tokens=anterior.orcamento_tokens,
        )
        sessao.add(nova)
        await sessao.flush()
        anteriores = f"{entrega.titulo}: {entrega.resumo}" if entrega else "(sem entrega)"
        trabalhar = Etapa(
            cadeia_id=nova.id,
            ordem=1,
            depende_de=[],
            especialista=escolhida.especialista,
            agente_id=escolhida.agente_id,
            titulo=f"Ajustar: {texto[:50]}",
            nivel=escolhida.nivel,
            tarefa=(
                f"O usuário pediu um ajuste: {texto}\n\nTarefa original: {escolhida.tarefa}\n"
                f"Entrega anterior: {anteriores}"
            ),
            status=StatusEtapa.PENDENTE,
        )
        conferir = Etapa(
            cadeia_id=nova.id,
            ordem=2,
            depende_de=[1],
            especialista="verificador",
            agente_id=verificacao.agente_id,
            titulo=verificacao.titulo,
            nivel=verificacao.nivel,
            tarefa=verificacao.tarefa,
            status=StatusEtapa.PENDENTE,
        )
        sessao.add_all([trabalhar, conferir])
        await sessao.flush()
        plano_anterior = anterior.plano or {}
        nova.plano = {
            "objetivo": plano_anterior.get("objetivo", texto),
            "requisitos": [*plano_anterior.get("requisitos", []), f"Ajuste: {texto}"],
            "etapas": [],
        }
        await sessao.commit()
        eventos = [
            EtapaPlanoEvento(
                etapa_id=e.id,
                ordem=e.ordem,
                especialista=e.especialista,
                agente_id=e.agente_id,
                titulo=e.titulo,
                nivel=Nivel(e.nivel),
                depende_de=list(e.depende_de),
            )
            for e in (trabalhar, conferir)
        ]
        await _publicar(
            ctx, nova, CadeiaCriada(cadeia_id=nova.id, versao=nova.versao, etapas=eventos)
        )
        await _publicar(
            ctx,
            nova,
            CadeiaAtualizada(
                cadeia_id=nova.id,
                status=nova.status,
                tokens_usados=nova.tokens_usados,
                custo_usd=_custo(nova),
            ),
        )
        nova_id = str(nova.id)
    await enfileirar("avancar_cadeia", cadeia_id=nova_id)
