"""Âncora-8: custo por chamada, passos da conversa direta e ``proposta`` do cartão (sem banco)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from app.agentes.middleware.custo import (
    MiddlewareCustoDasChamadas,
    custo_da_resposta,
    marcar_custo,
)
from app.agentes.middleware.passos import (
    PASSOS_DA_CONVERSA_IGNORADOS,
    MiddlewarePassos,
    desembrulhar_catalogo,
    id_do_turno,
)
from app.atencao import PedidoAtencao
from app.eventos.tipos import AprovacaoPedida
from app.ferramentas.propor_instrucoes import proposta_do_cartao


def _modelo(preco_entrada="1", preco_saida="2"):
    chat = SimpleNamespace(metadata=None)
    marcar_custo(
        chat,
        modelo="groq/m",
        provedor_id=uuid4(),
        nivel="N2",
        papel="agente_individual",
        preco_entrada=Decimal(preco_entrada),
        preco_saida=Decimal(preco_saida),
    )
    return chat


def _resposta(entrada=1_000_000, saida=500_000):
    mensagem = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": entrada,
            "output_tokens": saida,
            "total_tokens": entrada + saida,
        },
    )
    return SimpleNamespace(result=[mensagem])


def test_custo_da_chamada_usa_o_preco_do_catalogo():
    custo = custo_da_resposta(_modelo(), _resposta(), 120)
    assert custo is not None
    assert custo.papel == "agente_individual" and custo.nivel == "N2"
    assert (custo.tokens_entrada, custo.tokens_saida) == (1_000_000, 500_000)
    assert custo.custo_usd == Decimal("2.000000")  # 1 M x US$1 + 0,5 M x US$2
    assert custo.provedor_id is not None and custo.latencia_ms == 120


def test_sem_marca_do_seletor_ou_sem_uso_nao_grava():
    assert custo_da_resposta(SimpleNamespace(metadata=None), _resposta(), 1) is None  # falso
    assert custo_da_resposta(_modelo(), _resposta(0, 0), 1) is None  # provedor sem uso


async def test_middleware_grava_uma_linha_por_chamada_e_nunca_derruba_o_turno():
    gravadas = []

    async def gravar(custo):
        gravadas.append(custo)

    async def handler(_):
        return _resposta(10, 5)

    pedido = SimpleNamespace(model=_modelo())
    resposta = await MiddlewareCustoDasChamadas(gravar).awrap_model_call(pedido, handler)
    assert resposta.result[0].content == "ok" and len(gravadas) == 1

    async def quebrado(_):
        raise RuntimeError("banco fora")

    resposta = await MiddlewareCustoDasChamadas(quebrado).awrap_model_call(pedido, handler)
    assert resposta.result[0].content == "ok"


async def test_passos_ignoram_a_fala_e_anunciam_o_prompt():
    eventos = []

    async def iniciar(etapa_id, agente_id, chamada):
        eventos.append(("inicio", chamada["name"]))
        return chamada

    async def finalizar(passo, resultado, erro):
        eventos.append(("fim", passo["name"]))

    prompts = []

    async def anunciar(etapa_id, agente_id, texto):
        prompts.append(texto)

    middleware = MiddlewarePassos(
        uuid4(),
        uuid4(),
        iniciar=iniciar,
        finalizar=finalizar,
        anunciar_prompt=anunciar,
        ignorar=PASSOS_DA_CONVERSA_IGNORADOS,
    )
    estado = {"messages": [HumanMessage("primeira"), AIMessage("x"), HumanMessage("o pedido")]}
    await middleware.abefore_agent(estado, None)
    assert prompts == ["o pedido"]

    async def handler(_):
        return "resultado"

    for nome in ("falar", "perguntar", "conectores_buscar_ferramentas", "buscar_web"):
        pedido = SimpleNamespace(tool_call={"name": nome, "args": {}, "id": "1"})
        assert await middleware.awrap_tool_call(pedido, handler) == "resultado"
    assert eventos == [("inicio", "buscar_web"), ("fim", "buscar_web")]


def test_passo_pelo_catalogo_aparece_com_o_nome_real():
    real = desembrulhar_catalogo(
        {
            "name": "conectores_executar_ferramenta",
            "args": {"id": "ler_historico", "argumentos": {}},
        }
    )
    assert real["name"] == "ler_historico"


def test_id_do_turno_e_estavel_na_retomada_do_mesmo_pedido():
    a = SimpleNamespace(thread_proprio="conversa:1:pedido:2")
    b = SimpleNamespace(thread_proprio="conversa:1:pedido:3")
    assert id_do_turno(a) == id_do_turno(SimpleNamespace(thread_proprio="conversa:1:pedido:2"))
    assert id_do_turno(a) != id_do_turno(b)
    sem_thread = SimpleNamespace(thread_proprio=None)
    assert id_do_turno(sem_thread) != id_do_turno(sem_thread)


def test_proposta_so_existe_no_cartao_de_instrucoes():
    acao = {
        "ferramenta": "propor_instrucoes",
        "argumentos": {"instrucoes": "Novo texto", "motivo": "Porque sim", "diferenca": "-a\n+b"},
    }
    assert proposta_do_cartao(acao) == {
        "instrucoes": "Novo texto",
        "motivo": "Porque sim",
        "diferenca": "-a\n+b",
    }
    assert proposta_do_cartao({**acao, "argumentos": {"instrucoes": "x"}}) == {"instrucoes": "x"}
    assert proposta_do_cartao({"ferramenta": "esquecer_memoria", "argumentos": {}}) is None
    assert proposta_do_cartao(None) is None
    assert proposta_do_cartao({"ferramenta": "propor_instrucoes", "argumentos": {}}) is None


def test_proposta_some_do_json_quando_nao_ha_e_aparece_quando_ha():
    base = {
        "aprovacao_id": uuid4(),
        "resumo": "r",
        "dano": "d",
        "quem_recebe": None,
        "expira_em": datetime.now(UTC),
    }
    assert "proposta" not in AprovacaoPedida(**base).model_dump(mode="json")
    com = AprovacaoPedida(**base, proposta={"instrucoes": "novo"}).model_dump(mode="json")
    assert com["proposta"] == {"instrucoes": "novo"}
    pedido = {
        "id": uuid4(),
        "tipo": "aprovacao",
        "titulo": "t",
        "resumo": "r",
        "criado_em": datetime.now(UTC),
    }
    assert "proposta" not in PedidoAtencao(**pedido).model_dump(mode="json")
    com_proposta = PedidoAtencao(**pedido, proposta={"instrucoes": "n"})
    assert com_proposta.model_dump(mode="json")["proposta"] == {"instrucoes": "n"}
