"""B1 do Prumo-3: o raciocínio do modelo não volta ao provedor que o recusa (Motor, etapa 5)."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.llm.fabrica import criar_chat_model
from app.llm.mensagens import (
    aceita_raciocinio_no_historico,
    sem_campos_de_raciocinio,
)
from app.llm.provedores import ConfigProvedor
from app.modelos.enumeracoes import TipoProvedor


def _conversa_com_ferramenta() -> list[Any]:
    return [
        HumanMessage("Qual a capital da França?"),
        AIMessage(
            content="",
            tool_calls=[{"name": "buscar_web", "args": {"consulta": "capital"}, "id": "c1"}],
            additional_kwargs={"reasoning_content": "Vou buscar na web."},
        ),
        ToolMessage("Paris", tool_call_id="c1", name="buscar_web"),
    ]


class _ClienteFalso:
    """Fica no lugar do módulo ``litellm``: guarda exatamente o que seria enviado."""

    def __init__(self) -> None:
        self.chamadas: list[dict[str, Any]] = []

    async def acompletion(self, **kwargs: Any) -> Any:
        self.chamadas.append(kwargs)
        return {
            "choices": [
                {"message": {"role": "assistant", "content": "Paris."}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


def test_remove_os_campos_de_raciocinio_sem_mexer_no_resto() -> None:
    entrada = [
        {"role": "user", "content": "oi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1"}],
            "reasoning_content": "pensei",
            "reasoning": "x",
        },
    ]
    saida = sem_campos_de_raciocinio(entrada)
    assert saida == [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
    ]
    assert "reasoning_content" in entrada[1]  # a lista original não é alterada


@pytest.mark.parametrize(
    ("tipo", "aceita"),
    [
        (TipoProvedor.GROQ, False),
        (TipoProvedor.OPENAI, False),
        (TipoProvedor.COMPATIVEL_OPENAI, False),
        (TipoProvedor.OPENROUTER, False),
        (TipoProvedor.OLLAMA, False),
        (TipoProvedor.ANTHROPIC, False),
        (TipoProvedor.GOOGLE, True),
    ],
)
def test_so_quem_le_o_raciocinio_o_recebe_de_volta(tipo: TipoProvedor, aceita: bool) -> None:
    assert aceita_raciocinio_no_historico(tipo) is aceita


@pytest.mark.parametrize(
    ("tipo", "modelo", "vai"),
    [
        (TipoProvedor.GROQ, "groq/openai/gpt-oss-20b", False),
        (TipoProvedor.COMPATIVEL_OPENAI, "openai/qwen", False),
        (TipoProvedor.GOOGLE, "gemini/gemini-2.5-flash", True),
    ],
)
async def test_payload_enviado_ao_provedor(
    monkeypatch: pytest.MonkeyPatch, tipo: TipoProvedor, modelo: str, vai: bool
) -> None:
    monkeypatch.delenv("SORA_MODELO_FALSO", raising=False)
    config = ConfigProvedor(
        tipo=tipo,
        api_key="chave-de-teste",
        base_url="https://api.exemplo.com/v1" if tipo is TipoProvedor.COMPATIVEL_OPENAI else None,
    )
    chat = criar_chat_model(modelo, config, max_tokens=50)
    cliente = _ClienteFalso()
    chat.client = cliente  # type: ignore[assignment]

    resposta = await chat.ainvoke(_conversa_com_ferramenta())

    assert resposta.content == "Paris."
    (chamada,) = cliente.chamadas
    mensagens = chamada["messages"]
    assistente = next(m for m in mensagens if m["role"] == "assistant")
    assert assistente["tool_calls"][0]["id"] == "c1"  # a chamada de ferramenta segue intacta
    assert ("reasoning_content" in assistente) is vai
    if not vai:
        assert not any("reasoning" in chave for m in mensagens for chave in m)
    assert [m["role"] for m in mensagens] == ["user", "assistant", "tool"]
