from uuid import uuid4

import pytest

from app.api.agentes import _saida
from app.canais_equipe.modelos import TipoMensagemCanal
from app.canais_equipe.roteamento import Membro
from app.canais_equipe.servico import ArmazemCanaisEmMemoria, ServicoCanais
from app.eventos.equipe import (
    BotRascunhoEvento,
    BotRascunhoResolvido,
    GrupoPropostaResolvida,
    GrupoPropostoEvento,
)
from app.modelos.enumeracoes import Movimento, TipoAgente
from app.modelos.tabelas import Agente, RascunhoBot
from app.rascunhos_bot import RascunhoBotSaida, saida_do_rascunho


def test_agente_saida_expoe_ferramentas_efetivas_e_estado() -> None:
    agente = Agente(
        id=uuid4(),
        usuario_id=uuid4(),
        tipo=TipoAgente.INDIVIDUAL,
        nome="Lume",
        funcao="Pesquisa",
        papel="pesquisador",
        cor="#56A8FF",
        movimento=Movimento.VIBRACAO,
        ferramentas=["escrever_arquivo", "buscar_web"],
    )

    saida = _saida(agente, estado="trabalhando")

    assert saida.estado == "trabalhando"
    assert saida.ferramentas == [
        "buscar_web",
        "ler_pagina",
        "ler_anexo",
        "entregar",
        "escrever_arquivo",
    ]


def test_sora_saida_recebe_ferramentas_do_papel_sem_mudar_aparencia() -> None:
    sora = Agente(
        id=uuid4(),
        usuario_id=uuid4(),
        tipo=TipoAgente.SORA,
        nome="Sora",
        funcao="",
        papel="",
        cor="#E2ECFF",
        movimento=Movimento.GIRA,
        ferramentas=[],
    )

    saida = _saida(sora)

    assert saida.cor == "#E2ECFF"
    assert saida.movimento is Movimento.GIRA
    assert "perguntar" in saida.ferramentas
    assert saida.estado == "livre"


@pytest.mark.asyncio
async def test_resultado_do_grupo_carrega_anexos_na_mensagem() -> None:
    usuario, sora, bot, anexo = uuid4(), uuid4(), uuid4(), uuid4()
    armazem = ArmazemCanaisEmMemoria()
    servico = ServicoCanais(armazem)
    canal = await servico.criar(
        usuario_id=usuario,
        nome="Grupo",
        membros=[sora, bot],
        lider_id=sora,
        agentes_do_usuario={sora, bot},
    )
    mudancas = await servico.mensagem_do_usuario(
        canal.id,
        usuario,
        texto="Prepare o arquivo",
        destinatario=bot,
        membros=[Membro(sora, "Sora", "Chefe"), Membro(bot, "Lume", "Pesquisa")],
    )
    tarefa = await servico.iniciar(mudancas.tarefas[0].id)

    resultado = await servico.registrar_resultado(
        tarefa.id, tarefa.revisao, por_agente=bot, texto="Pronto.", anexos=[anexo]
    )

    assert resultado.mensagens[0].tipo is TipoMensagemCanal.RESULTADO
    assert resultado.mensagens[0].anexos == (anexo,)


def test_eventos_do_rascunho_preservam_formato_do_cartao() -> None:
    rascunho = RascunhoBot(
        id=uuid4(),
        usuario_id=uuid4(),
        dados={
            "nome": "Lume",
            "funcao": "Pesquisa",
            "cor": "#56A8FF",
            "instrucoes": "Pesquise fontes confiáveis.",
            "ferramentas": ["buscar_web"],
            "rotina": None,
        },
    )

    evento = BotRascunhoEvento.de(saida_do_rascunho(rascunho))
    resolvido = BotRascunhoResolvido(
        rascunho_id=rascunho.id, status="confirmado", agente_id=uuid4()
    )

    assert evento.model_dump(mode="json")["status"] == "rascunho"
    assert evento.model_dump(mode="json")["nome"] == "Lume"
    assert resolvido.status == "confirmado"


def test_eventos_da_proposta_sao_editaveis_antes_da_resolucao() -> None:
    novo = RascunhoBotSaida(
        id=uuid4(),
        nome="Lume",
        funcao="Pesquisa",
        cor="#56A8FF",
        instrucoes="Pesquise.",
        ferramentas=["buscar_web"],
        rotina=None,
    )
    proposta = GrupoPropostoEvento(
        id=uuid4(),
        nome="Lançamento",
        pedido="Preparar o lançamento",
        bots_reaproveitados=[],
        bots_novos=[novo],
    )
    resolvida = GrupoPropostaResolvida(proposta_id=proposta.id, status="recusada")

    assert proposta.status == "proposta"
    assert proposta.bots_novos[0].nome == "Lume"
    assert resolvida.grupo_id is None


# ---------- rodada 2026-11-08: @todos, cartão no turno de grupo, bot apagado ----------


def test_todos_vai_so_para_os_bots_e_nao_para_a_sora_lider() -> None:
    from app.canais_equipe.roteamento import rotear

    sora, lume, nexo = uuid4(), uuid4(), uuid4()
    membros = [Membro(sora, "Sora", "Chefe"), Membro(lume, "Lume"), Membro(nexo, "Nexo")]
    rota = rotear(
        texto="@todos revisem o texto",
        membros=membros,
        lider_id=sora,
        tarefas=[],
        mensagens={},
    )
    assert rota.tipo == "donos"
    assert set(rota.agentes) == {lume, nexo}
    assert rota.texto == "revisem o texto"


def test_cartao_da_interrupcao_le_aprovacao_e_ignora_turno_sem_pausa() -> None:
    from langgraph.types import Interrupt

    from app.canais_equipe.pausa import cartao_da_interrupcao

    cartao = str(uuid4())
    assert (
        cartao_da_interrupcao(
            {"__interrupt__": [Interrupt(value={"tipo": "aprovacao", "aprovacao_id": cartao})]}
        )
        == cartao
    )
    assert cartao_da_interrupcao({"messages": []}) is None
    assert cartao_da_interrupcao({"__interrupt__": [Interrupt(value="texto")]}) is None


def test_ferramentas_no_grupo_tira_as_de_conversa_e_cadeia() -> None:
    from workers.equipe import ferramentas_no_grupo

    bot = Agente(papel="individual", ferramentas=["gerar_imagem", "entregar"])
    assert ferramentas_no_grupo(bot) == [
        "ler_anexo",
        "buscar_web",
        "ler_pagina",
        "escrever_arquivo",
        "gerar_imagem",
    ]
    assert ferramentas_no_grupo(None) == []


async def _grupo_com_tarefa_rodando():
    usuario, sora, bot = uuid4(), uuid4(), uuid4()
    armazem = ArmazemCanaisEmMemoria()
    servico = ServicoCanais(armazem)
    canal = await servico.criar(
        usuario_id=usuario,
        nome="Grupo",
        membros=[sora, bot],
        lider_id=sora,
        agentes_do_usuario={sora, bot},
    )
    mudancas = await servico.mensagem_do_usuario(
        canal.id,
        usuario,
        texto="Envie o relatório",
        destinatario=bot,
        membros=[Membro(sora, "Sora", "Chefe"), Membro(bot, "Lume", "Pesquisa")],
    )
    tarefa = await servico.iniciar(mudancas.tarefas[0].id)
    return servico, usuario, canal, bot, tarefa


async def test_pausar_para_decisao_e_retomar_o_mesmo_turno() -> None:
    from app.canais_equipe.modelos import MotivoParada, StatusTarefa

    servico, _, _, _, tarefa = await _grupo_com_tarefa_rodando()
    revisao, turno = tarefa.revisao, tarefa.turno_seq

    mudancas = await servico.pausar_para_decisao(tarefa.id, revisao)
    assert [t.status for t in mudancas.tarefas] == [StatusTarefa.PARADA]
    assert mudancas.tarefas[0].motivo is MotivoParada.AGUARDANDO_DECISAO
    assert "decisão" in mudancas.mensagens[0].texto
    # Revisão velha não retoma; a certa retoma rodando no mesmo turno, com revisão nova.
    assert await servico.retomar_decisao(tarefa.id, revisao + 5) is None
    retomada = await servico.retomar_decisao(tarefa.id, revisao)
    assert retomada is not None
    assert retomada.status is StatusTarefa.RODANDO and retomada.motivo is None
    assert retomada.revisao == revisao + 1 and retomada.turno_seq == turno
    # A decisão consumida não retoma de novo.
    assert await servico.retomar_decisao(tarefa.id, revisao) is None


async def test_decisao_nao_acorda_tarefa_que_o_usuario_retomou_a_mao() -> None:
    servico, usuario, _, _, tarefa = await _grupo_com_tarefa_rodando()
    revisao = tarefa.revisao
    await servico.pausar_para_decisao(tarefa.id, revisao)
    await servico.retomar(tarefa.id, usuario, disponiveis={tarefa.dono_id})
    assert await servico.retomar_decisao(tarefa.id, revisao) is None


async def test_bot_apagado_sai_do_grupo_e_o_trabalho_dele_e_cancelado() -> None:
    from app.canais_equipe.modelos import StatusTarefa

    servico, usuario, canal, bot, tarefa = await _grupo_com_tarefa_rodando()
    mudancas = await servico.remover_agente_apagado(canal.id, usuario, bot, "Lume")
    assert bot not in (await servico.canal(canal.id)).membros
    assert [t.status for t in mudancas.tarefas] == [StatusTarefa.CANCELADA]
    assert mudancas.interromper == [tarefa.id]
    assert "Lume foi apagado" in mudancas.mensagens[0].texto
    repetida = await servico.remover_agente_apagado(canal.id, usuario, bot, "Lume")
    assert not repetida.tarefas and not repetida.mensagens


def test_cartao_de_envio_vira_enviar_descartar_e_o_resto_aprovar_recusar() -> None:
    from app.atencao import _texto_acao
    from app.modelos.tabelas import Aprovacao

    envio = Aprovacao(
        acao={
            "ferramenta": "conectores_executar_ferramenta",
            "argumentos": {
                "id": "gmail_send_email",
                "argumentos": {"to": "cliente@exemplo.com", "subject": "Relatório"},
            },
        }
    )
    tipo, titulo, resumo = _texto_acao(envio)
    assert (tipo, titulo) == ("rascunho_envio", "Revisar envio")
    assert resumo == "Para cliente@exemplo.com · Relatório"
    apagar = Aprovacao(acao={"ferramenta": "esquecer_memoria", "argumentos": {"id": "x"}})
    assert _texto_acao(apagar)[0] == "aprovacao"
    instrucoes = Aprovacao(
        acao={
            "ferramenta": "propor_instrucoes",
            "argumentos": {"instrucoes": "Falar formal.", "motivo": "Pedido seu."},
        }
    )
    tipo, _, resumo = _texto_acao(instrucoes, "Ravi")
    assert tipo == "aprovacao"
    assert resumo == (
        "Ravi quer mudar as próprias instruções. Novas instruções: “Falar formal.” "
        "Motivo: Pedido seu."
    )
    assert _texto_acao(apagar, "Sora")[2] == "Sora quer apagar uma memória."
    conector = Aprovacao(
        acao={"ferramenta": "chamar_conector", "argumentos": {"id": "notion_criar_pagina"}},
        avaliacao={"motivo": "Cria uma página no Notion."},
    )
    assert _texto_acao(conector, "Ravi")[2] == (
        "Ravi quer usar um conector (notion criar pagina). Cria uma página no Notion."
    )


def test_modelo_falso_sora_propoe_grupo_e_bot_pergunta() -> None:
    from langchain_core.messages import HumanMessage

    from app.llm.falso import _gatilho_pendente

    grupo = _gatilho_pendente("sora", [HumanMessage("Lance minha loja [grupo]")])
    assert grupo.tool_calls[0]["name"] == "propor_grupo"
    assert grupo.tool_calls[0]["args"]["pedido"] == "Lance minha loja"
    assert _gatilho_pendente("agente_individual", [HumanMessage("x [grupo]")]) is None
    pergunta = _gatilho_pendente("agente_individual", [HumanMessage("Resuma [pergunta]")])
    assert pergunta.tool_calls[0]["name"] == "perguntar"
    aprovacao = _gatilho_pendente("agente_individual", [HumanMessage("Mude [aprovacao]")])
    assert aprovacao.tool_calls[0]["name"] == "propor_instrucoes"


@pytest.mark.parametrize(
    ("pedido", "esperado"),
    [
        ("  Primeiro nome  \nOutra linha", "Primeiro nome"),
        ("", "Novo grupo"),
        ("x" * 90, "x" * 60),
        ("a" * 30 + " " + "b" * 35, "a" * 30),
        ("a" * 60, "a" * 60),
    ],
)
def test_nome_do_pedido(pedido: str, esperado: str) -> None:
    from app.api.grupos import nome_do_pedido

    assert nome_do_pedido(pedido) == esperado


def test_rota_de_aprovar_versao_nao_e_registrada() -> None:
    from app.main import criar_aplicacao

    assert "/v1/conversas/{conversa_id}/aprovar" not in criar_aplicacao().openapi()["paths"]
