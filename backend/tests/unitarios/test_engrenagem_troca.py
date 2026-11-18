"""Engrenagem: troca de modelo no meio de um turno com ferramenta já executada.

A troca (``ModelRetryMiddleware`` + ``ModelFallbackMiddleware``) só repete a CHAMADA AO MODELO:
a ferramenta que já rodou não roda de novo, e o reserva recebe o histórico com a chamada e o
resultado casados. O ajuste do pedido (``MiddlewarePedidoValido``) é o do modelo que responde.
"""

from __future__ import annotations

from typing import Any

import litellm
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import Field

from app.agentes.middleware.pedido_valido import MiddlewarePedidoValido
from app.llm.troca import montar_middleware_de_troca


class Modelo(GenericFakeChatModel):
    model: str = "groq/principal"
    falhar_depois_da_ferramenta: bool = False
    recebidas: list[list[Any]] = Field(default_factory=list)
    vinculadas: list[list[Any]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        self.vinculadas.append(list(tools))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
        self.recebidas.append(list(messages))
        if self.falhar_depois_da_ferramenta and any(isinstance(m, ToolMessage) for m in messages):
            raise litellm.RateLimitError(message="429", llm_provider="groq", model=self.model)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


async def test_reserva_continua_sem_repetir_a_ferramenta() -> None:
    execucoes: list[str] = []

    @tool
    async def agir(argumentos: dict) -> str:
        """Faz algo com efeito."""
        execucoes.append("x")
        return "feito"

    principal = Modelo(
        falhar_depois_da_ferramenta=True,
        messages=iter(
            [AIMessage("", tool_calls=[{"name": "agir", "args": {"argumentos": {}}, "id": "c1"}])]
            + [AIMessage("nunca")] * 5
        ),
    )
    reserva = Modelo(model="gemini/gemini-2.5-flash", messages=iter([AIMessage("pronto")]))
    agente = create_agent(
        principal,
        tools=[agir],
        middleware=[
            *montar_middleware_de_troca([principal, reserva], espera_inicial_s=0),
            MiddlewarePedidoValido(),
        ],
    )
    resultado = await agente.ainvoke({"messages": [HumanMessage("faça")]})
    assert execucoes == ["x"]
    assert resultado["messages"][-1].content == "pronto"
    (historico,) = reserva.recebidas
    chamada = next(m for m in historico if isinstance(m, AIMessage) and m.tool_calls)
    resposta = historico[historico.index(chamada) + 1]
    assert isinstance(resposta, ToolMessage) and resposta.tool_call_id == "c1"
    # O reserva é Gemini: recebeu o esquema ajustado (objeto aberto vira texto com JSON).
    (vinculada,) = reserva.vinculadas[0]
    assert vinculada["function"]["parameters"]["properties"]["argumentos"]["type"] == "string"
    assert not isinstance(principal.vinculadas[0][0], dict)
