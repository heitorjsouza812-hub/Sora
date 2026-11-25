"""Engrenagem: o pedido ao modelo sai num formato que o provedor aceita.

- esquemas de TODAS as ferramentas do registro e das meta-ferramentas do catálogo, convertidos
  como o LangChain/LiteLLM fazem, conferidos contra as regras dos provedores;
- Gemini: objeto aberto vira texto com JSON e volta a ser objeto antes da ferramenta;
- histórico sem chamada de ferramenta órfã (400 na OpenAI, Anthropic e Groq).
"""

from __future__ import annotations

import copy
import inspect
import json
import re
from typing import Any
from uuid import uuid4

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from app.agentes.middleware.pedido_valido import MiddlewarePedidoValido
from app.agentes.montagem import ContextoAgente, montar_agente
from app.ferramentas.base import ContextoFerramenta
from app.ferramentas.catalogo_preguicoso import montar_catalogo
from app.ferramentas.registro import ESQUEMAS, criar_ferramentas
from app.llm.esquemas import (
    RESPOSTA_INTERROMPIDA,
    argumentos_lidos,
    ferramenta_para_gemini,
    historico_valido,
    modelo_gemini,
)
from app.llm.falso import criar_modelo_falso


async def _permitir(ferramenta: BaseTool, argumentos: dict[str, Any]) -> None:
    pass


def _todas_as_ferramentas() -> list[BaseTool]:
    contexto = ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4())
    ferramentas = criar_ferramentas(list(ESQUEMAS), contexto)
    return [
        *ferramentas,
        *montar_catalogo(
            ferramentas, prefixo="conectores", limite_direto=0, antes_de_executar=_permitir
        ),
        *montar_catalogo(
            ferramentas[:3], prefixo="navegador", limite_direto=0, antes_de_executar=_permitir
        ),
    ]


def test_registro_tem_todas_as_ferramentas_e_o_catalogo_tres_meta() -> None:
    nomes = [f.name for f in _todas_as_ferramentas()]
    assert len(nomes) == len(set(nomes)) == len(ESQUEMAS) + 6


@pytest.mark.parametrize("ferramenta", _todas_as_ferramentas(), ids=lambda f: f.name)
def test_esquema_aceito_por_openai_groq_e_anthropic(ferramenta: BaseTool) -> None:
    from litellm.llms.anthropic.chat.transformation import AnthropicConfig

    openai = convert_to_openai_tool(ferramenta)
    funcao = openai["function"]
    assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", funcao["name"])
    assert not funcao["name"].startswith("mcp_") or funcao["name"].startswith("mcp__")
    assert funcao["description"].strip()
    parametros = funcao["parameters"]
    assert parametros["type"] == "object"
    assert "properties" in parametros
    texto = json.dumps(parametros)
    assert "$ref" not in texto and "$defs" not in texto  # Groq e Gemini recusam referência
    assert len(texto) < 8_000
    anthropic = AnthropicConfig()._map_tool_helper(copy.deepcopy(openai))
    anthropic = anthropic[0] if isinstance(anthropic, tuple) else anthropic
    assert anthropic["input_schema"]["type"] == "object"


def _objetos_abertos(esquema: Any, caminho: str = "") -> list[str]:
    achados: list[str] = []
    if isinstance(esquema, dict):
        if str(esquema.get("type", "")).lower() == "object" and not esquema.get("properties"):
            achados.append(caminho or "<raiz>")
        for chave, valor in esquema.items():
            achados += _objetos_abertos(valor, f"{caminho}.{chave}")
    elif isinstance(esquema, list):
        for indice, valor in enumerate(esquema):
            achados += _objetos_abertos(valor, f"{caminho}[{indice}]")
    return achados


@pytest.mark.parametrize("ferramenta", _todas_as_ferramentas(), ids=lambda f: f.name)
def test_esquema_para_gemini_sem_objeto_aberto(ferramenta: BaseTool) -> None:
    from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import (
        VertexGeminiConfig,
    )

    ajustada = ferramenta_para_gemini(convert_to_openai_tool(ferramenta))
    (ferramentas,) = VertexGeminiConfig()._map_function([ajustada], {})
    (declaracao,) = ferramentas["function_declarations"]
    assert _objetos_abertos(declaracao.get("parameters")) == []


def test_sem_ajuste_o_gemini_receberia_objeto_aberto() -> None:
    """Prova do defeito: o LiteLLM sozinho deixa ``argumentos`` como objeto sem propriedades."""
    from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import (
        VertexGeminiConfig,
    )

    meta = {f.name: f for f in _todas_as_ferramentas()}["conectores_executar_ferramenta"]
    (ferramentas,) = VertexGeminiConfig()._map_function([convert_to_openai_tool(meta)], {})
    assert ".properties.argumentos" in _objetos_abertos(
        ferramentas["function_declarations"][0]["parameters"]
    )


def test_argumentos_em_texto_voltam_a_ser_objeto_so_onde_o_esquema_pede() -> None:
    meta = {f.name: f for f in _todas_as_ferramentas()}
    esquema = convert_to_openai_tool(meta["conectores_executar_ferramenta"])["function"][
        "parameters"
    ]
    lidos = argumentos_lidos(esquema, {"id": "x", "argumentos": '{"a": 1}'})
    assert lidos == {"id": "x", "argumentos": {"a": 1}}
    # texto que não é JSON fica como veio (a validação devolve o erro ao modelo)
    assert argumentos_lidos(esquema, {"id": "x", "argumentos": "a=1"})["argumentos"] == "a=1"
    falar = convert_to_openai_tool(meta["falar"])["function"]["parameters"]
    assert argumentos_lidos(falar, {"texto": '{"a": 1}'}) == {"texto": '{"a": 1}'}


def test_modelo_gemini_pelo_nome() -> None:
    assert modelo_gemini("gemini/gemini-2.5-flash")
    assert modelo_gemini("vertex_ai/gemini-2.0-flash")
    assert not modelo_gemini("groq/llama-3.3-70b-versatile")
    assert not modelo_gemini("openrouter/google/gemini-2.5-flash")


# ---------- histórico ----------


def _chamada(*ids: str, nome: str = "buscar_web") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": nome, "args": {}, "id": i} for i in ids])


def _pares_validos(mensagens: list[Any]) -> bool:
    for indice, mensagem in enumerate(mensagens):
        if isinstance(mensagem, AIMessage) and mensagem.tool_calls:
            seguintes = mensagens[indice + 1 : indice + 1 + len(mensagem.tool_calls)]
            if [getattr(m, "tool_call_id", None) for m in seguintes] != [
                c["id"] for c in mensagem.tool_calls
            ]:
                return False
        if isinstance(mensagem, ToolMessage):
            anterior = next(
                (m for m in reversed(mensagens[:indice]) if isinstance(m, AIMessage)), None
            )
            if anterior is None or mensagem.tool_call_id not in {
                c["id"] for c in anterior.tool_calls
            }:
                return False
    return True


def test_chamada_orfa_de_turno_interrompido_ganha_resposta() -> None:
    mensagens = [HumanMessage("a"), _chamada("c1", "c2"), HumanMessage("b")]
    consertado = historico_valido(mensagens)
    assert not _pares_validos(mensagens)
    assert _pares_validos(consertado)
    assert [m.content for m in consertado if isinstance(m, ToolMessage)] == [
        RESPOSTA_INTERROMPIDA,
        RESPOSTA_INTERROMPIDA,
    ]


def test_resposta_fora_do_lugar_sobe_e_solta_sai() -> None:
    mensagens = [
        HumanMessage("a"),
        _chamada("c1"),
        SystemMessage("lembrete"),
        ToolMessage("r1", tool_call_id="c1"),
        ToolMessage("solta", tool_call_id="zz"),
        AIMessage("fim"),
    ]
    consertado = historico_valido(mensagens)
    assert _pares_validos(consertado)
    assert [m.content for m in consertado] == ["a", "", "r1", "lembrete", "fim"]


def test_historico_certo_volta_igual() -> None:
    mensagens = [HumanMessage("a"), _chamada("c1"), ToolMessage("r", tool_call_id="c1")]
    assert historico_valido(mensagens) is mensagens


# ---------- dentro do agente ----------


class Gravador(GenericFakeChatModel):
    """Modelo de roteiro que guarda o que recebeu e as ferramentas vinculadas."""

    model: str = "groq/llama-3.3-70b-versatile"
    recebidas: list[list[Any]] = Field(default_factory=list)
    vinculadas: list[list[Any]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        self.vinculadas.append(list(tools))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
        self.recebidas.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _executar_ferramenta() -> tuple[StructuredTool, list[Any]]:
    recebidos: list[Any] = []

    async def acao(**argumentos: Any) -> str:
        recebidos.append(argumentos)
        return "ok"

    conectores = [
        StructuredTool.from_function(coroutine=acao, name=f"mcp__s__a{i}", description="x")
        for i in range(2)
    ]
    executar = montar_catalogo(conectores, limite_direto=0, antes_de_executar=_permitir)[2]
    return executar, recebidos


async def test_gemini_recebe_esquema_ajustado_e_argumento_em_texto_vira_objeto() -> None:
    executar, _ = _executar_ferramenta()
    modelo = Gravador(
        model="gemini/gemini-2.5-flash",
        recebidas=[],
        vinculadas=[],
        messages=iter(
            [
                AIMessage(
                    "",
                    tool_calls=[
                        {
                            "name": "conectores_executar_ferramenta",
                            "args": {"id": "mcp__s__a1", "argumentos": "{}"},
                            "id": "c1",
                        }
                    ],
                ),
                AIMessage("fim"),
            ]
        ),
    )
    agente = create_agent(modelo, tools=[executar], middleware=[MiddlewarePedidoValido()])
    resultado = await agente.ainvoke({"messages": [HumanMessage("faz")]})
    (vinculada,) = modelo.vinculadas[0]
    assert isinstance(vinculada, dict)
    argumentos = vinculada["function"]["parameters"]["properties"]["argumentos"]
    assert argumentos["type"] == "string"
    resposta = next(m for m in resultado["messages"] if isinstance(m, ToolMessage))
    assert resposta.status != "error" and resposta.content == "ok"


async def test_outro_provedor_recebe_as_ferramentas_como_estao() -> None:
    executar, _ = _executar_ferramenta()
    modelo = Gravador(recebidas=[], vinculadas=[], messages=iter([AIMessage("oi")]))
    agente = create_agent(modelo, tools=[executar], middleware=[MiddlewarePedidoValido()])
    await agente.ainvoke({"messages": [HumanMessage("faz")]})
    assert modelo.vinculadas[0] == [executar]


async def test_thread_com_chamada_orfa_nao_quebra_a_chamada_seguinte() -> None:
    modelo = Gravador(recebidas=[], vinculadas=[], messages=iter([AIMessage("oi")]))
    agente = create_agent(modelo, tools=[], middleware=[MiddlewarePedidoValido()])
    await agente.ainvoke(
        {"messages": [HumanMessage("a"), _chamada("c1", nome="falar"), HumanMessage("b")]}
    )
    assert _pares_validos(modelo.recebidas[0])


def test_argumentos_em_texto_dentro_de_lista_de_objetos() -> None:
    meta = {f.name: f for f in _todas_as_ferramentas()}
    esquema = convert_to_openai_tool(meta["navegador_lote"])["function"]["parameters"]
    passos = [{"ferramenta": "navegador_acao", "args": '{"ref": "@s1:e2"}'}]
    lidos = argumentos_lidos(esquema, {"passos": passos})
    assert lidos["passos"][0]["args"] == {"ref": "@s1:e2"}


@pytest.mark.parametrize("papel", ["pesquisador", "individual"])
async def test_montagem_do_agente_entrega_apenas_executores_com_revisao(
    monkeypatch: pytest.MonkeyPatch, papel
) -> None:
    async def conectores_do_usuario(*args, **kwargs) -> list[StructuredTool]:
        async def consultar() -> str:
            pytest.fail("A montagem do agente nunca executa ferramentas")

        return [
            StructuredTool.from_function(
                coroutine=consultar,
                name=f"mcp__inventario__get_item_{i}",
                description="Consulta um item",
            )
            for i in range(25)
        ]

    async def prompt_de_teste(contexto: ContextoAgente) -> str:
        return "Conversa de teste"

    entregues: list[BaseTool] = []

    def capturar_ferramentas(*, tools, **kwargs) -> None:
        entregues.extend(tools)

    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    monkeypatch.setattr("app.agentes.montagem._prompt_do_turno", prompt_de_teste)
    monkeypatch.setattr("app.conectores.carregar.ferramentas_dos_conectores", conectores_do_usuario)
    monkeypatch.setattr("langchain.agents.create_agent", capturar_ferramentas)

    contexto = ContextoAgente(
        usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4(), papel=papel
    )
    await montar_agente(contexto, [criar_modelo_falso(papel)], checkpointer=None)

    executores = [f for f in entregues if f.name.endswith("_executar_ferramenta")]
    assert "conectores_executar_ferramenta" in {f.name for f in executores}
    for executor in executores:
        assert isinstance(executor, StructuredTool) and executor.coroutine is not None
        gancho = inspect.getclosurevars(executor.coroutine).nonlocals.get("antes_de_executar")
        assert callable(gancho), executor.name
