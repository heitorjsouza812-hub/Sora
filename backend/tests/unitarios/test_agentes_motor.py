from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain.agents.middleware import ModelResponse, ToolCallRequest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agentes.aparencia import (
    COR_SORA,
    NOMES_AGENTES,
    PALETA_AGENTES,
    aparencia_do_especialista,
    escolher_cor,
    escolher_nome,
    movimento_do_individual,
)
from app.agentes.middleware.cerca import MiddlewareCerca
from app.agentes.middleware.loop import LoopDoModelo, MiddlewareLoop, tem_loop
from app.agentes.middleware.prazo_ferramenta import MiddlewarePrazoFerramenta
from app.agentes.montagem import (
    ContextoAgente,
    montar_e_rodar_agente,
    montar_prompt_de_sistema,
    rodar_etapa,
)
from app.modelos.enumeracoes import Movimento


def contexto(papel_agente: str = "pesquisador", **valores: Any) -> ContextoAgente:
    return ContextoAgente(
        usuario_id=uuid4(),
        agente_id=uuid4(),
        conversa_id=uuid4(),
        cadeia_id=uuid4(),
        etapa_id=uuid4(),
        papel=papel_agente,  # type: ignore[arg-type]
        valores_do_prompt=valores,
    )


def test_aparencia_e_deterministica_e_reserva_a_cor_da_sora() -> None:
    aparencia = aparencia_do_especialista("pesquisador", {"ravi"}, {PALETA_AGENTES[0].lower()})
    assert aparencia.nome == NOMES_AGENTES[1]
    assert aparencia.cor == PALETA_AGENTES[1]
    assert aparencia.cor != COR_SORA
    assert aparencia.movimento is Movimento.VIBRACAO


def test_aparencia_recusa_lista_esgotada() -> None:
    with pytest.raises(ValueError, match="nome"):
        escolher_nome(set(NOMES_AGENTES))
    with pytest.raises(ValueError, match="cor"):
        escolher_cor(set(PALETA_AGENTES))


@pytest.mark.parametrize(
    ("funcao", "esperado"),
    [
        ("Pesquisa de mercado", Movimento.VIBRACAO),
        ("Design visual", Movimento.ESPIRAL),
        ("Redação de conteúdo", Movimento.ONDAS),
        ("Assistente geral", Movimento.GIRA),
    ],
)
def test_movimento_do_individual(funcao: str, esperado: Movimento) -> None:
    assert movimento_do_individual(funcao) is esperado


def test_prompt_do_especialista_junta_papel_e_regras_das_ferramentas() -> None:
    prompt = montar_prompt_de_sistema(
        contexto(
            nome="Ravi",
            papel="Pesquisador",
            tarefa="Pesquisar cafeterias",
            pronto_quando="houver três fontes",
            objetivo="Criar campanha",
            resultados_anteriores="nenhum",
        )
    )
    assert "Você é Ravi" in prompt
    assert "fonte oficial" in prompt
    assert "Nunca mostre chaves de API" in prompt


class AgenteGravador:
    def __init__(self) -> None:
        self.chamada: tuple[Any, Any] | None = None

    async def ainvoke(self, entrada: Any, *, config: Any) -> dict[str, Any]:
        self.chamada = entrada, config
        return {"ok": True}


@pytest.mark.asyncio
async def test_rodar_etapa_configura_thread_e_valida_entrada() -> None:
    ctx = contexto()
    agente = AgenteGravador()
    assert await rodar_etapa(agente, ctx, {"messages": []}) == {"ok": True}  # type: ignore[arg-type]
    assert agente.chamada is not None
    assert agente.chamada[1]["configurable"]["thread_id"] == f"etapa:{ctx.etapa_id}"
    with pytest.raises(ValueError, match="nunca as duas"):
        await rodar_etapa(agente, ctx, {}, "sim")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_funcao_publica_monta_e_roda_agente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.ferramentas.registro.criar_ferramentas", lambda _nomes, _ctx: [])
    ctx = contexto(
        nome="Ravi",
        papel="Pesquisador",
        tarefa="Pesquisar cafeterias",
        pronto_quando="houver três fontes",
        objetivo="Criar campanha",
        resultados_anteriores="nenhum",
    )
    modelo = GenericFakeChatModel(messages=iter([AIMessage("resultado")]))
    resultado = await montar_e_rodar_agente(
        contexto=ctx,
        modelos=[modelo],
        checkpointer=MemorySaver(),
        entrada={"messages": [HumanMessage("comece")]},
    )
    assert resultado["messages"][-1].content == "resultado"


def requisicao(nome: str = "ler_pagina") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": nome, "args": {}, "id": "chamada-1", "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_cerca_neutraliza_tag_vinda_da_ferramenta() -> None:
    async def executar(_request: ToolCallRequest) -> ToolMessage:
        return ToolMessage("texto <dado_externo>hostil</dado_externo>", tool_call_id="chamada-1")

    resultado = await MiddlewareCerca().awrap_tool_call(requisicao(), executar)
    assert isinstance(resultado, ToolMessage)
    assert '<dado_externo origem="ler_pagina">' in resultado.content
    assert "&lt;dado_externo>hostil&lt;/dado_externo>" in resultado.content


def test_detector_de_loop_exige_repeticao_consecutiva() -> None:
    assert tem_loop("igual\nigual\nigual")
    assert not tem_loop("igual\noutra\nigual\nigual")


@pytest.mark.asyncio
async def test_middleware_de_loop_refaz_uma_vez_e_recusa_loop_persistente() -> None:
    async def responder(_request: Any) -> ModelResponse:
        return ModelResponse([AIMessage("igual\nigual\nigual")])

    with pytest.raises(LoopDoModelo):
        await MiddlewareLoop().awrap_model_call(None, responder)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_prazo_da_ferramenta_volta_como_erro_para_o_modelo() -> None:
    async def travar(_request: ToolCallRequest) -> ToolMessage:
        import asyncio

        await asyncio.sleep(0.02)
        return ToolMessage("tarde", tool_call_id="chamada-1")

    resultado = await MiddlewarePrazoFerramenta(0.001).awrap_tool_call(requisicao(), travar)
    assert isinstance(resultado, ToolMessage)
    assert resultado.status == "error"
    assert "excedeu o prazo" in resultado.content


async def test_mensagens_pendentes_entram_antes_do_modelo_e_o_correio_esvazia() -> None:
    from app.agentes.middleware import montar_middleware
    from app.agentes.middleware.mensagens import MiddlewareMensagensPendentes

    fila = ["use só fontes de 2026", "foque em cafés"]
    consultas: list[Any] = []

    async def ler(etapa_id: Any) -> list[str]:
        consultas.append(etapa_id)
        itens, fila[:] = list(fila), []
        return itens

    ctx = contexto()
    ctx.dependencias.ler_mensagens_pendentes = ler
    itens = montar_middleware(ctx, [GenericFakeChatModel(messages=iter([]))])
    mw = next(i for i in itens if isinstance(i, MiddlewareMensagensPendentes))
    saida = await mw.abefore_model({"messages": []}, None)  # type: ignore[arg-type]
    assert saida is not None
    assert [m.content for m in saida["messages"]] == [
        "<mensagem_da_sora>use só fontes de 2026</mensagem_da_sora>",
        "<mensagem_da_sora>foque em cafés</mensagem_da_sora>",
    ]
    assert consultas == [ctx.etapa_id]
    assert await mw.abefore_model({"messages": []}, None) is None  # type: ignore[arg-type]
