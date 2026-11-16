"""O seletor mantém só chats e limita os destaques por provedor."""

import pytest

from app.llm.catalogo_chat import modelo_de_chat, modelos_principais


@pytest.mark.parametrize(
    "nome",
    [
        "groq/whisper-large-v3",
        "openai/tts-1",
        "gemini/embedding-001",
        "groq/llama-guard-4-12b",
        "openai/gpt-audio",
        "openai/gpt-realtime",
        "groq/canopylabs/orpheus-v1-english",
    ],
)
def test_outros_usos_nao_sao_chat(nome):
    assert not modelo_de_chat(nome)


def test_curadoria_e_fallback():
    nomes = ["openai/gpt-4o", "openai/gpt-4o-mini", "openai/o3", "openai/tts-1"]
    assert modelos_principais(nomes) == {"openai/gpt-4o", "openai/o3"}
    assert modelos_principais([f"ollama/modelo-{i}" for i in range(8)]) == {
        f"ollama/modelo-{i}" for i in range(4)
    }
