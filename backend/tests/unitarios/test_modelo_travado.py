"""Bot "pensando" para sempre (2026-11-21): o Gemini sobrecarregado deixava a chamada pendurada,
sem prazo, e o bot com ferramentas do computador só tinha modelos do Google na lista.

Provas: toda chamada dos bots tem prazo; prazo estourado vai direto para a reserva (sem repetir o
modelo pendurado); Gemini 3 em diante recebe a temperatura padrão; e o bot do computador tem
reservas de outro provedor logo depois do melhor modelo com visão.
"""

from __future__ import annotations

from typing import Any

import litellm
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import Field, SecretStr

from app.agentes.visao import ordenar_com_reservas
from app.llm import fabrica
from app.llm.provedores import ConfigProvedor
from app.llm.troca import deve_repetir_no_mesmo, deve_trocar, montar_middleware_de_troca
from app.modelos.enumeracoes import TipoProvedor


class _Modelo(GenericFakeChatModel):
    model: str = "gemini/gemini-3.8-flash"
    pendurado: bool = False
    chamadas: list[int] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
        self.chamadas.append(1)
        if self.pendurado:
            # o que o ChatLiteLLM levanta quando o prazo da chamada estoura
            raise litellm.Timeout(message="prazo", model=self.model, llm_provider="gemini")
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def test_prazo_troca_de_modelo_mas_nao_repete_o_mesmo() -> None:
    prazo = litellm.Timeout(message="x", model="m", llm_provider="gemini")
    sobrecarga = litellm.ServiceUnavailableError(message="503", model="m", llm_provider="gemini")
    limite = litellm.RateLimitError(message="429", model="m", llm_provider="groq")
    chave = litellm.AuthenticationError(message="401", model="m", llm_provider="groq")
    assert deve_trocar(prazo) and not deve_repetir_no_mesmo(prazo)
    assert deve_trocar(sobrecarga) and deve_repetir_no_mesmo(sobrecarga)
    assert deve_trocar(limite) and deve_repetir_no_mesmo(limite)
    assert not deve_trocar(chave) and not deve_repetir_no_mesmo(chave)
    assert not deve_repetir_no_mesmo(TimeoutError())


async def test_modelo_pendurado_passa_a_vez_para_a_reserva_uma_vez_so() -> None:
    principal = _Modelo(pendurado=True, messages=iter([AIMessage("nunca")]))
    reserva = _Modelo(model="groq/qwen/qwen3.8-27b", messages=iter([AIMessage("tabela pronta")]))
    agente = create_agent(principal, middleware=montar_middleware_de_troca([principal, reserva]))
    resultado = await agente.ainvoke({"messages": [HumanMessage("monte a tabela")]})
    assert resultado["messages"][-1].content == "tabela pronta"
    assert len(principal.chamadas) == 1  # sem a segunda espera no modelo pendurado
    assert len(reserva.chamadas) == 1


def test_toda_chamada_dos_bots_tem_prazo_e_gemini_3_vai_com_temperatura_padrao(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(fabrica, "modelo_falso_ativo", lambda: False)
    google = ConfigProvedor(tipo=TipoProvedor.GOOGLE, api_key=SecretStr("k"))
    groq = ConfigProvedor(tipo=TipoProvedor.GROQ, api_key=SecretStr("k"))
    gemini, qwen = fabrica.criar_modelos_na_ordem(
        [("gemini/gemini-3.8-flash", google), ("groq/qwen/qwen3.8-27b", groq)]
    )
    assert gemini.request_timeout == fabrica.PRAZO_CHAMADA_S
    assert qwen.request_timeout == fabrica.PRAZO_CHAMADA_S
    assert gemini.temperature == 1.0  # abaixo de 1 o Gemini 3 entra em laço
    assert qwen.temperature == 0.0
    for nome, esperado in (
        ("gemini/gemini-3.8-flash", True),
        ("gemini/gemini-3.1-flash-lite-image", True),
        ("gemini/gemini-10-pro", True),
        ("gemini/antigravity-preview-05-2026", True),
        ("gemini/gemini-2.5-flash", False),
        ("groq/qwen/qwen3.8-27b", False),
        ("openai/gpt-5", False),
    ):
        assert fabrica.exige_temperatura_padrao(nome) is esperado, nome


class _Nome:
    def __init__(self, model: str) -> None:
        self.model = model


def test_bot_do_computador_tem_reserva_de_outro_provedor_logo_depois_do_primeiro() -> None:
    com_visao = [_Nome(n) for n in ("gemini/a", "gemini/b", "gemini/c")]
    reservas = [_Nome(n) for n in ("groq/x", "gemini/a", "groq/y", "gemini/d")]
    ordem = [m.model for m in ordenar_com_reservas(com_visao, reservas)]
    assert ordem == ["gemini/a", "groq/x", "groq/y", "gemini/b", "gemini/c", "gemini/d"]
    assert [m.model for m in ordenar_com_reservas([], reservas)] == [m.model for m in reservas]


async def test_monitor_de_saude_conta_a_falha_do_travado_e_a_resposta_da_reserva() -> None:
    falhas: list[tuple[str, str]] = []
    respostas: list[str] = []

    async def falhou(modelo: Any, erro: BaseException) -> None:
        falhas.append((modelo.model, type(erro).__name__))

    async def respondeu(modelo: Any) -> None:
        respostas.append(modelo.model)

    principal = _Modelo(pendurado=True, messages=iter([AIMessage("nunca")]))
    reserva = _Modelo(model="groq/qwen/qwen3.8-27b", messages=iter([AIMessage("ok")]))
    agente = create_agent(
        principal,
        middleware=montar_middleware_de_troca(
            [principal, reserva], ao_falhar=falhou, ao_responder=respondeu
        ),
    )
    await agente.ainvoke({"messages": [HumanMessage("oi")]})
    assert falhas == [("gemini/gemini-3.8-flash", "Timeout")]
    assert respostas == ["groq/qwen/qwen3.8-27b"]


def test_provedor_do_modelo_vem_da_marca_de_custo() -> None:
    from uuid import uuid4

    from app.agentes.middleware.custo import marcar_custo
    from app.llm.saude import provedor_do_modelo

    modelo = _Modelo(messages=iter([]))
    assert provedor_do_modelo(modelo) is None  # modelo falso dos testes: nada a contar
    provedor = uuid4()
    marcar_custo(
        modelo,
        modelo="gemini/gemini-3.8-flash",
        provedor_id=provedor,
        nivel="N1",
        papel="individual",
        preco_entrada=None,
        preco_saida=None,
    )
    assert provedor_do_modelo(modelo) == provedor
