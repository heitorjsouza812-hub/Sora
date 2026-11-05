"""Política de aprovação aplicada na execução de cada ferramenta (Âncora, etapa 4).

Peças do Rakazo (``docs/referencias/rakazo.md``): ``politica.py`` diz *o que* pede aprovação e
``juiz.py`` roda o juiz rápido. Aqui elas se encontram na hora da chamada:

- ``livre``: roda;
- ``cartao_fixo``: sempre abre o cartão (nem a regra "sempre permitir" dispensa);
- ``revisor``: uma regra "sempre permitir" do usuário libera; senão o juiz decide, e qualquer
  dúvida, erro ou prazo estourado vira cartão (falha fechada);
- rotina sem supervisão: só roda o que ``pode_sem_supervisao`` aceita.

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
from app.modelos.enumeracoes import AutorMensagem, DecisaoAprovacao, StatusAprovacao
from app.modelos.tabelas import Aprovacao, Mensagem
from app.revisor.esquemas import AcaoProposta, DecisaoRevisor
from app.revisor.politica import Politica, pode_sem_supervisao, politica_da_ferramenta

registro = logging.getLogger(__name__)

VALIDADE_DO_CARTAO = timedelta(minutes=10)

CUIDAM_DO_PROPRIO_CARTAO: set[str] = {"criar_agente"}
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

    async with abrir_sessao() as sessao:
        modelos = await modelos_do_papel(sessao, contexto.usuario_id, "revisor", dificuldade=1)
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
    return AcaoProposta(ferramenta=nome, argumentos=argumentos)


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
        ),
    )
    from app.ferramentas.criar_agente import _agendar_expiracao

    await _agendar_expiracao(aprovacao_id, expira_em)
    return aprovacao_id


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


async def conferir_acao(
    nome: str,
    argumentos: dict[str, Any],
    contexto: ContextoFerramenta,
    *,
    chamada_id: str,
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
    politica = politica_da_ferramenta(nome, somente_leitura=somente_leitura)
    if politica is Politica.LIVRE:
        return None

    proposta = await _preparar_acao(nome, argumentos, contexto)
    acao = {
        **proposta.model_dump(mode="json"),
        "conversa_id": str(contexto.conversa_id),
        "chamada_id": chamada_id,
    }
    resumo = rotulo_do_passo(nome, argumentos)
    existente = await _cartao_existente(contexto, acao)
    avaliacao: dict[str, Any] = {"modelo_revisor": False, "dano": "baixo"}
    dano = (
        "Muda algo na sua conta."
        if politica is Politica.CARTAO_FIXO
        else "Tem efeito fora da Sora."
    )
    quem_recebe: str | None = None

    if existente is None:
        if politica is Politica.REVISOR:
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
    await _registrar(contexto, proposta, resumo, aprovacao_id)
    return None
