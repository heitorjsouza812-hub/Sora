"""Política de aprovação aplicada na execução de cada ferramenta (Âncora, etapa 4).

Peças do Rakazo (``docs/referencias/rakazo.md``): ``politica.py`` diz *o que* pede aprovação e
``juiz.py`` roda o juiz rápido. Aqui elas se encontram na hora da chamada:

- ``livre``: roda;
- ``cartao_fixo``: sempre abre o cartão (nem a regra "sempre permitir" dispensa);
- ``revisor``: uma regra "sempre permitir" do usuário libera; senão o juiz decide, e qualquer
  dúvida, erro ou prazo estourado vira cartão (falha fechada);
- rotina sem supervisão: só roda o que ``pode_sem_supervisao`` aceita;
- modo de permissão da conversa (seletor do campo de mensagem, Âncora-9): ``automatico`` aprova
  sozinho o que é de risco baixo e ``total`` tudo o que a política deixaria aprovar, nunca os
  bloqueios absolutos (``revisor/decisoes.py``). A aprovação automática fica em
  ``registro_acoes`` e aparece no painel Trabalho como "Aprovado automaticamente (modo X)".

O cartão usa a interrupção do LangGraph, como ``criar_agente``: o job termina, a etapa fica em
``aguardando_aprovacao`` e a decisão volta por ``Command(resume=…)``. Ao retomar, o nó roda de
novo desde o início; por isso o cartão é achado pela ``chamada_id`` e nunca duplicado nem
rejulgado.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from langgraph.types import interrupt
from sqlalchemy import select

from app.eventos.tipos import AprovacaoPedida
from app.ferramentas.ambiente import emitir
from app.ferramentas.base import ContextoFerramenta
from app.ferramentas.infra import abrir_sessao
from app.ferramentas.propor_instrucoes import proposta_do_cartao
from app.modelos.enumeracoes import AutorMensagem, DecisaoAprovacao, StatusAprovacao
from app.modelos.tabelas import Aprovacao, Mensagem
from app.revisor.esquemas import AcaoProposta, DecisaoRevisor
from app.revisor.politica import Politica, pode_sem_supervisao, politica_da_ferramenta

registro = logging.getLogger(__name__)

VALIDADE_DO_CARTAO = timedelta(minutes=10)

CUIDAM_DO_PROPRIO_CARTAO: set[str] = {"criar_agente", "propor_grupo"}
"""Ferramentas que abrem o próprio cartão. Quem criar outra com cartão próprio acrescenta aqui."""

PREFIXOS_PROPRIOS = (
    "conectores_executar_ferramenta",
    "navegador_executar_ferramenta",
    "navegador_buscar_ferramentas",
    "navegador_carregar_ferramenta",
)
"""A meta-ferramenta de execução do catálogo preguiçoso é revisada com o nome da ferramenta de
verdade, no gancho do catálogo.

``navegador_*`` **não** está aqui: a revisão de domínio do navegador (Leme) só cuida de domínio
novo em perfil logado, dentro de ``navegador_abrir``. Clicar, digitar, tecla e lote
(``navegador_acao``, ``navegador_tecla``, ``navegador_lote``, ``navegador_agir``) têm efeito e
passam pelo juiz e pelo cartão como qualquer ferramenta; observar, procurar, esperar e capturar
são leitura (política ``livre``) e rodam direto."""

NEGADO = "O usuário não aprovou esta ação. Não tente de novo; siga sem ela e avise o usuário."
SEM_SUPERVISAO = (
    "Esta ferramenta não pode rodar numa rotina sem o usuário presente. "
    "Registre uma pendência ou avise o usuário na próxima conversa."
)


def cuida_do_proprio_cartao(nome: str) -> bool:
    return nome in CUIDAM_DO_PROPRIO_CARTAO or nome.startswith(PREFIXOS_PROPRIOS)


async def _pedidos_do_usuario(contexto: ContextoFerramenta) -> list[str]:
    async with abrir_sessao() as sessao:
        linhas = await sessao.scalars(
            select(Mensagem.conteudo)
            .where(
                Mensagem.conversa_id == contexto.conversa_id,
                Mensagem.autor == AutorMensagem.USUARIO,
            )
            .order_by(Mensagem.criada_em.desc())
            .limit(5)
        )
        return list(reversed(list(linhas)))


async def chamar_modelo_revisor(contexto: ContextoFerramenta, sistema: str, prompt: str) -> str:
    """Juiz rápido no modelo do papel ``revisor`` do usuário (o modelo falso bloqueia)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.orquestrador.modelos import modelos_do_papel
    from app.preferencias_conversa import escolha_efetiva

    async with abrir_sessao() as sessao:
        # contrato do seletor (Âncora-10): o juiz também respeita o modelo/raciocínio da conversa
        escolha = await escolha_efetiva(
            sessao,
            contexto.usuario_id,
            conversa_id=contexto.conversa_id,
            agente_id=contexto.agente_id,
        )
        modelos = await modelos_do_papel(
            sessao, contexto.usuario_id, "revisor", dificuldade=1, escolha=escolha
        )
    resposta = await modelos[0].ainvoke([SystemMessage(sistema), HumanMessage(prompt)])
    conteudo = resposta.content
    return conteudo if isinstance(conteudo, str) else str(conteudo)


async def _preparar_acao(
    nome: str, argumentos: dict[str, Any], contexto: ContextoFerramenta
) -> AcaoProposta:
    if nome == "propor_instrucoes":
        from app.ferramentas.pecas import instrucoes_atuais
        from app.ferramentas.propor_instrucoes import ProporInstrucoes, preparar_proposta

        return preparar_proposta(
            ProporInstrucoes(**argumentos), contexto, await instrucoes_atuais(contexto.agente_id)
        )
    if nome == "computador_agir":
        # alvo explícito: a regra "sempre permitir" fica presa a ele (Cerca M3)
        argumentos = {**argumentos, "alvo": argumentos.get("alvo") or "virtual"}
    return AcaoProposta(ferramenta=nome, argumentos=argumentos)


def _sem_texto_digitado(valor: Any) -> Any:
    """Troca todo ``texto`` de ações de computador por ``[N caracteres]`` (Cerca B1).

    O cartão fica em ``aprovacoes.acao`` sem prazo; o que o bot quer digitar no computador
    (inclusive no PC do usuário) não fica guardado nele. A busca do cartão ao retomar continua
    exata, porque a ``chamada_id`` já identifica a chamada.
    """
    if isinstance(valor, dict):
        return {
            chave: (
                f"[{len(item)} caracteres]"
                if chave == "texto" and isinstance(item, str)
                else _sem_texto_digitado(item)
            )
            for chave, item in valor.items()
        }
    if isinstance(valor, list):
        return [_sem_texto_digitado(item) for item in valor]
    return valor


def acao_do_cartao(
    nome: str, proposta: AcaoProposta, contexto: ContextoFerramenta, chamada_id: str
) -> dict[str, Any]:
    """O que fica gravado no cartão (``aprovacoes.acao``)."""
    acao = {
        **proposta.model_dump(mode="json"),
        "conversa_id": str(contexto.conversa_id),
        "chamada_id": chamada_id,
    }
    if nome.startswith("computador_"):
        acao["argumentos"] = _sem_texto_digitado(acao.get("argumentos"))
    return acao


async def _cartao_existente(
    contexto: ContextoFerramenta, acao: dict[str, Any]
) -> tuple[UUID, StatusAprovacao] | None:
    async with abrir_sessao() as sessao:
        cartao = await sessao.scalar(
            select(Aprovacao)
            .where(
                Aprovacao.usuario_id == contexto.usuario_id,
                Aprovacao.agente_id == contexto.agente_id,
                Aprovacao.etapa_id == contexto.etapa_id,
                Aprovacao.acao == acao,
            )
            .order_by(Aprovacao.expira_em.desc())
            .limit(1)
        )
        return None if cartao is None else (cartao.id, cartao.status)


async def _abrir_cartao(
    contexto: ContextoFerramenta,
    acao: dict[str, Any],
    avaliacao: dict[str, Any],
    resumo: str,
    dano: str,
    quem_recebe: str | None,
) -> UUID:
    expira_em = datetime.now(UTC) + VALIDADE_DO_CARTAO
    async with abrir_sessao() as sessao:
        cartao = Aprovacao(
            usuario_id=contexto.usuario_id,
            etapa_id=contexto.etapa_id,
            agente_id=contexto.agente_id,
            grupo_id=contexto.canal_id,
            acao=acao,
            avaliacao=avaliacao,
            status=StatusAprovacao.PENDENTE,
            expira_em=expira_em,
        )
        sessao.add(cartao)
        await sessao.flush()
        aprovacao_id = cartao.id
    await emitir(
        contexto,
        AprovacaoPedida(
            aprovacao_id=aprovacao_id,
            resumo=resumo,
            dano=dano,
            quem_recebe=quem_recebe,
            expira_em=expira_em,
            agente_id=contexto.agente_id,
            conversa_id=contexto.conversa_id,
            bot_id=contexto.agente_id,
            grupo_id=contexto.canal_id,
            proposta=proposta_do_cartao(acao),
        ),
    )
    from app.atencao import publicar_estado_atencao_persistido

    await publicar_estado_atencao_persistido(
        contexto.usuario_id, agente_id=contexto.agente_id, grupo_id=contexto.canal_id
    )
    from app.ferramentas.criar_agente import _agendar_expiracao

    await _agendar_expiracao(aprovacao_id, expira_em)
    await _soltar_vez_do_pc(contexto)
    return aprovacao_id


async def _soltar_vez_do_pc(contexto: ContextoFerramenta) -> None:
    """Esperando o cartão, o bot não mexe no PC do usuário: devolve a vez (Cerca A2).

    Com a vez presa, ``api/aprovacoes.py`` recusa a decisão de qualquer sessão (o bot poderia
    clicar na Sora web). Solta só se a vez for deste bot; quem segue depois pega de novo.
    """
    from app.computador.pc_usuario_canal import CanalPc
    from app.ferramentas.infra import obter_redis

    try:
        await CanalPc(obter_redis()).soltar_vez(contexto.usuario_id, contexto.agente_id)
    except Exception:  # sem Redis o cartão continua valendo; só a vez fica até vencer
        registro.warning("não consegui soltar a vez do PC ao abrir o cartão", exc_info=True)


async def _registrar(
    contexto: ContextoFerramenta, proposta: AcaoProposta, resumo: str, aprovacao_id: UUID | None
) -> None:
    from app.revisor.acoes import registrar_acao

    async with abrir_sessao() as sessao:
        await registrar_acao(
            sessao,
            contexto.usuario_id,
            contexto.agente_id,
            contexto.etapa_id,
            proposta,
            resumo,
            aprovacao_id,
        )


async def modo_de_permissao(contexto: ContextoFerramenta) -> str:
    """Modo da conversa (ou do grupo, ou o padrão do bot). Rotina sem supervisão: ``perguntar``."""
    if contexto.sem_supervisao:
        return "perguntar"
    if contexto.permissao is not None:
        return contexto.permissao
    from app.preferencias_conversa import escolha_da_execucao

    escolha = await escolha_da_execucao(
        contexto.usuario_id, contexto.conversa_id, contexto.agente_id
    )
    return escolha.permissao


async def perfil_do_bot_tem_login(contexto: ContextoFerramenta) -> bool:
    """O navegador do bot tem login salvo? Na dúvida, ``True`` (falha fechada)."""
    try:
        from app.navegador.perfis import particao, perfil_tem_login
        from app.navegador.repositorio import RepositorioNavegador

        repositorio = RepositorioNavegador(abrir_sessao)
        escolha = await repositorio.escolha_do_agente(contexto.agente_id, contexto.usuario_id)
        if escolha is None:
            return False  # perfil efêmero: nada salvo
        estado = await repositorio.ler_estado(
            particao(contexto.usuario_id, contexto.agente_id, escolha)
        )
        return perfil_tem_login(estado)
    except Exception:
        registro.warning("não consegui ler o perfil do navegador do bot", exc_info=True)
        return True


async def anunciar_aprovacao_automatica(
    contexto: ContextoFerramenta,
    nome: str,
    modo: str,
    resumo: str,
    proposta: AcaoProposta | None = None,
) -> None:
    """Registra a ação aprovada pelo modo e mostra o passo "Aprovado automaticamente (modo X)"
    no painel Trabalho. Falha ao publicar nunca derruba a ferramenta."""
    from uuid import NAMESPACE_URL, uuid4, uuid5

    from app.eventos.tipos import PassoEvento
    from app.modelos.enumeracoes import StatusPasso, TipoPasso
    from app.revisor.decisoes import texto_aprovado_automaticamente

    texto = texto_aprovado_automaticamente(modo, resumo)
    await _registrar(
        contexto, proposta or AcaoProposta(ferramenta=nome, argumentos={}), texto, None
    )
    etapa = (
        contexto.etapa_painel
        or contexto.etapa_id
        or uuid5(NAMESPACE_URL, f"sora:aprovacao-automatica:{contexto.conversa_id}")
    )
    try:
        await emitir(
            contexto,
            PassoEvento(
                passo_id=uuid4(),
                etapa_id=etapa,
                agente_id=contexto.agente_id,
                tipo=TipoPasso.PENSAMENTO,
                texto=texto,
                ferramenta=nome,
                status=StatusPasso.CONCLUIDO,
                resultado={"aprovacao": "automatica", "modo": modo},
            ),
        )
    except Exception:
        registro.warning("não consegui publicar a aprovação automática", exc_info=True)


async def conferir_acao(
    nome: str,
    argumentos: dict[str, Any],
    contexto: ContextoFerramenta,
    *,
    chamada_id: str,
    chamada_legada: str | None = None,
    cartoes_retomados: set[str] | None = None,
    somente_leitura: bool | None = None,
) -> str | None:
    """``None`` = pode rodar. Texto = resultado que volta ao modelo no lugar da ferramenta."""
    from app.ferramentas.rotulos import rotulo_do_passo
    from app.revisor.acoes import regra_permite
    from app.revisor.juiz import avaliar_acao

    if cuida_do_proprio_cartao(nome):
        return None
    if contexto.sem_supervisao and not pode_sem_supervisao(nome, somente_leitura=somente_leitura):
        return SEM_SUPERVISAO
    if nome == "computador_agir":
        from app.computador.teclado_local import marcar

        marcar(False)  # vale só para esta chamada; quem dispensa o juiz marca de novo abaixo
    politica = politica_da_ferramenta(nome, somente_leitura=somente_leitura)
    if politica is Politica.LIVRE:
        return None

    proposta = await _preparar_acao(nome, argumentos, contexto)
    acao = acao_do_cartao(nome, proposta, contexto, chamada_id)
    resumo = rotulo_do_passo(nome, argumentos)
    existente = await _cartao_existente(contexto, acao)
    if existente is None and chamada_legada and cartoes_retomados:
        anterior = await _cartao_existente(contexto, {**acao, "chamada_id": chamada_legada})
        if anterior and str(anterior[0]) in cartoes_retomados:
            existente = anterior
    avaliacao: dict[str, Any] = {"modelo_revisor": False, "dano": "baixo"}
    dano = (
        "Muda algo na sua conta."
        if politica is Politica.CARTAO_FIXO
        else "Tem efeito fora da Sora."
    )
    if nome == "gerar_video":
        from app.ferramentas.gerar_video import texto_do_custo

        dano = texto_do_custo(argumentos)
    quem_recebe: str | None = None

    if existente is None:
        from app.revisor.contaminacao import modo_efetivo

        # Conteúdo de fora lido neste turno: o "total" vale como "automático" (prompt injection).
        modo = modo_efetivo(await modo_de_permissao(contexto), contexto)
        if modo != "perguntar":
            from app.revisor.decisoes import aprova_sozinho

            bruta = proposta.model_dump(mode="json")  # com o texto digitado (o cartão não tem)
            com_login = (
                await perfil_do_bot_tem_login(contexto) if nome.startswith("navegador_") else True
            )
            if aprova_sozinho(
                modo, bruta, sem_supervisao=contexto.sem_supervisao, perfil_tem_login=com_login
            ):
                await anunciar_aprovacao_automatica(contexto, nome, modo, resumo, proposta)
                return None
        from app.revisor.decisoes import bloqueio_absoluto

        # Nem regras anteriores nem o juiz podem liberar um bloqueio permanente sozinhos.
        bloqueada = bloqueio_absoluto(proposta.model_dump(mode="json")) is not None
        if politica is Politica.REVISOR and not bloqueada:
            from app.computador.teclado_local import dispensa_juiz, marcar

            if dispensa_juiz(nome, argumentos):
                # Vela-12: teclado de edição no PC do usuário; a ponte só aceita editores locais
                # nesta chamada (``app/computador/teclado_local.py``)
                marcar(True)
                await _registrar(contexto, proposta, resumo, None)
                return None
            async with abrir_sessao() as sessao:
                liberada = await regra_permite(
                    sessao, contexto.usuario_id, contexto.agente_id, proposta
                )
            if liberada:
                await _registrar(contexto, proposta, resumo, None)
                return None
            veredito = await avaliar_acao(
                lambda s, p: chamar_modelo_revisor(contexto, s, p),
                proposta,
                await _pedidos_do_usuario(contexto),
            )
            if veredito.decisao is DecisaoRevisor.PERMITIR:
                await _registrar(contexto, proposta, resumo, None)
                return None
            avaliacao = {"modelo_revisor": True, **veredito.model_dump(mode="json")}
            dano = veredito.motivo or dano
            quem_recebe = veredito.quem_recebe
        aprovacao_id = await _abrir_cartao(contexto, acao, avaliacao, resumo, dano, quem_recebe)
        status = StatusAprovacao.PENDENTE
    else:
        aprovacao_id, status = existente

    if status is StatusAprovacao.PENDENTE:
        decisao = interrupt({"tipo": "aprovacao", "aprovacao_id": str(aprovacao_id)})
    elif status is StatusAprovacao.PERMITIDA:
        decisao = DecisaoAprovacao.PERMITIR_UMA_VEZ
    else:
        decisao = DecisaoAprovacao.NEGAR
    if str(decisao) in (DecisaoAprovacao.NEGAR.value, StatusAprovacao.NEGADA.value, "expirada"):
        return NEGADO
    from app.revisor.decisoes import e_envio

    if e_envio(acao):
        from app.modelos.tabelas import RegistroAcao
        from app.revisor.acoes import registrar_acao

        # A reserva é confirmada antes da chamada externa. Se o destino recebeu o envio e
        # a resposta se perdeu, uma repetição deste job não envia de novo.
        async with abrir_sessao() as sessao:
            decisao_gravada = await sessao.scalar(
                select(Aprovacao.status).where(Aprovacao.id == aprovacao_id).with_for_update()
            )
            if decisao_gravada != StatusAprovacao.PERMITIDA:
                return NEGADO
            usado = await sessao.scalar(
                select(RegistroAcao.id).where(RegistroAcao.aprovacao_id == aprovacao_id).limit(1)
            )
            if usado:
                return "Esta aprovação de envio já foi usada. Confira o destino antes de continuar."
            await registrar_acao(
                sessao,
                contexto.usuario_id,
                contexto.agente_id,
                contexto.etapa_id,
                proposta,
                resumo,
                aprovacao_id,
            )
    else:
        await _registrar(contexto, proposta, resumo, aprovacao_id)
    return None
