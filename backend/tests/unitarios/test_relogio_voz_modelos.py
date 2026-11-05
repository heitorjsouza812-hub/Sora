"""Modelos de voz de provedor compatível com a OpenAI (Groq etc.): escolhidos pela lista do
provedor, com um servidor HTTP local fazendo o papel dele."""

from __future__ import annotations

import asyncio
import socket
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import SecretStr

from app.api.voz import _escolher_modelo
from app.llm.provedores import ConfigProvedor, PoliticaRede
from app.modelos.enumeracoes import TipoProvedor
from app.voz.modelos import modelo_de_fala, modelo_de_transcricao
from app.voz.provedores import VozOpenAI

LOCAL = PoliticaRede(producao=False, rede_local=True)


def test_escolha_pela_lista() -> None:
    nomes = [
        "openai/llama-3.3-70b",
        "openai/distil-whisper-large-v3-en",
        "openai/whisper-large-v3",
        "openai/whisper-large-v3-turbo",
        "openai/playai-tts",
        "openai/canopylabs/orpheus-v1-english",
    ]
    assert modelo_de_transcricao(nomes) == "whisper-large-v3"
    assert modelo_de_fala(nomes) == "playai-tts"
    assert (
        modelo_de_transcricao(["gpt-4o-mini-transcribe", "whisper-1"]) == "gpt-4o-mini-transcribe"
    )
    assert modelo_de_fala(["llama", "mixtral"]) is None
    assert modelo_de_transcricao([]) is None


def _porta() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def _provedor(modelos: list[str] | None, visto: dict[str, Any]):
    app = FastAPI()

    @app.get("/openai/v1/models")
    async def lista() -> Any:
        if modelos is None:
            return Response(status_code=404)
        return {"data": [{"id": m} for m in modelos]}

    @app.post("/openai/v1/audio/transcriptions")
    async def transcricao(req: Request) -> dict:
        visto["auth"] = req.headers["authorization"]
        visto["corpo"] = (await req.body()).decode("latin-1")
        return {"text": "ola"}

    @app.post("/openai/v1/audio/speech")
    async def fala(req: Request) -> Response:
        visto["fala"] = await req.json()
        return Response(b"mp3", media_type="audio/mpeg")

    porta = _porta()
    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning")
    )
    tarefa = asyncio.create_task(servidor.serve())
    while not servidor.started:  # noqa: ASYNC110
        await asyncio.sleep(0.05)
    return servidor, tarefa, f"http://127.0.0.1:{porta}/openai/v1"


async def _rodar(modelos: list[str] | None, uso: str):
    visto: dict[str, Any] = {}
    servidor, tarefa, base = await _provedor(modelos, visto)
    try:
        config = ConfigProvedor(
            tipo=TipoProvedor.COMPATIVEL_OPENAI, api_key=SecretStr("gsk-x"), base_url=base
        )
        async with httpx.AsyncClient(trust_env=False) as cliente:
            voz = VozOpenAI("gsk-x", cliente=cliente)
            voz.api = base
            await _escolher_modelo(voz, config, cliente, LOCAL, uso)
            if uso == "transcricao":
                await voz.transcrever(b"audio", "audio/webm", "pt")
            else:
                await voz.sintetizar("oi", "alloy")
        return voz, visto
    finally:
        servidor.should_exit = True
        await tarefa


async def test_groq_transcreve_com_whisper_da_lista() -> None:
    voz, visto = await _rodar(["llama-3.3-70b", "whisper-large-v3", "playai-tts"], "transcricao")
    assert voz.modelo_transcricao == "whisper-large-v3"
    assert "whisper-large-v3" in visto["corpo"] and "gpt-4o-mini" not in visto["corpo"]
    assert visto["auth"] == "Bearer gsk-x"


async def test_groq_fala_com_tts_da_lista() -> None:
    voz, visto = await _rodar(["llama-3.3-70b", "whisper-large-v3", "playai-tts"], "fala")
    assert voz.modelo_fala == "playai-tts"
    assert visto["fala"]["model"] == "playai-tts"


async def test_sem_modelo_de_fala_vira_aviso_ptbr_nao_500() -> None:
    with pytest.raises(HTTPException) as erro:
        await _rodar(["llama-3.3-70b", "whisper-large-v3"], "fala")
    assert erro.value.status_code == 404
    assert "Configurações → Modelos de IA" in erro.value.detail
    with pytest.raises(HTTPException) as erro:
        await _rodar(["llama-3.3-70b"], "transcricao")
    assert erro.value.status_code == 404


async def test_lista_indisponivel_usa_o_nome_mais_comum() -> None:
    voz, visto = await _rodar(None, "transcricao")
    assert voz.modelo_transcricao == "whisper-1" and "whisper-1" in visto["corpo"]
