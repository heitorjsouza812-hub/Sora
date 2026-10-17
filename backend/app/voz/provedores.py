"""Provedores de voz com a chave do usuário: sintetizar (texto → MP3) e transcrever
(áudio → texto).

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``openai-voice.ts``,
``elevenlabs-voice.ts``, ``cartesia-voice.ts``, ``fish-audio-voice.ts`` e ``voice-http.ts``
(prazo de 60 s, áudio limitado, erro sem a chave).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.parse import quote

import httpx

from app.core.redacao import sanitizar_erro

NomeVoz = Literal["openai", "elevenlabs", "cartesia", "fish"]
PRAZO_SEGUNDOS = 60
MAX_BYTES_AUDIO = 20 * 1024 * 1024
MAX_CARACTERES_FALA = 4_000


class ErroVoz(Exception):
    """Falha do provedor de voz (mensagem sem a chave)."""


@dataclass(frozen=True, slots=True)
class Audio:
    conteudo: bytes
    tipo: str = "audio/mpeg"


class ProvedorVoz(Protocol):
    nome: str

    async def sintetizar(self, texto: str, voz: str) -> Audio: ...

    async def transcrever(
        self, audio: bytes, tipo: str = "audio/webm", idioma: str = "pt"
    ) -> str: ...


def _extensao(tipo: str) -> str:
    return {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
    }.get(tipo.split(";")[0].strip().lower(), "webm")


class _Base:
    nome: str = ""
    api: str = ""

    def __init__(self, chave: str, *, cliente: httpx.AsyncClient | None = None) -> None:
        self._chave = chave
        self._cliente = cliente

    async def _pedir(
        self, metodo: str, caminho: str, acao: str, **kwargs: object
    ) -> httpx.Response:
        proprio = self._cliente is None
        cliente = self._cliente or httpx.AsyncClient(timeout=PRAZO_SEGUNDOS, trust_env=False)
        try:
            resposta = await cliente.request(metodo, f"{self.api}{caminho}", **kwargs)  # type: ignore[arg-type]
        except httpx.TimeoutException as erro:
            raise ErroVoz(f"A voz ({self.nome}) demorou demais {acao}.") from erro
        except httpx.HTTPError as erro:
            raise ErroVoz(
                f"Não consegui falar com a voz ({self.nome}): {sanitizar_erro(erro, [self._chave])}"
            ) from erro
        finally:
            if proprio:
                await cliente.aclose()
        if resposta.status_code in (401, 403):
            raise ErroVoz(f"A chave da voz ({self.nome}) foi recusada.")
        if resposta.status_code == 429:
            raise ErroVoz(f"A voz ({self.nome}) chegou no limite. Tente daqui a pouco.")
        if resposta.status_code >= 400:
            raise ErroVoz(f"A voz ({self.nome}) respondeu {resposta.status_code} {acao}.")
        if len(resposta.content) > MAX_BYTES_AUDIO:
            raise ErroVoz("O áudio passou do tamanho máximo.")
        return resposta

    @staticmethod
    def _conferir_texto(texto: str) -> str:
        texto = texto.strip()
        if not texto:
            raise ErroVoz("Nada para falar.")
        return texto[:MAX_CARACTERES_FALA]

    @staticmethod
    def _texto_json(resposta: httpx.Response) -> str:
        try:
            return str(resposta.json().get("text", "")).strip()
        except (ValueError, AttributeError) as erro:
            raise ErroVoz("A transcrição voltou num formato inválido.") from erro


class VozOpenAI(_Base):
    nome = "openai"
    api = "https://api.openai.com/v1"
    modelo_fala = "gpt-4o-mini-tts"
    modelo_transcricao = "gpt-4o-mini-transcribe"

    def _cabecalhos(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._chave}"}

    async def sintetizar(self, texto: str, voz: str = "alloy") -> Audio:
        resposta = await self._pedir(
            "POST",
            "/audio/speech",
            "ao falar",
            headers=self._cabecalhos(),
            json={
                "model": self.modelo_fala,
                "voice": voz,
                "input": self._conferir_texto(texto),
                "response_format": "mp3",
            },
        )
        return Audio(resposta.content)

    async def transcrever(self, audio: bytes, tipo: str = "audio/webm", idioma: str = "pt") -> str:
        resposta = await self._pedir(
            "POST",
            "/audio/transcriptions",
            "ao transcrever",
            headers=self._cabecalhos(),
            data={"model": self.modelo_transcricao, "language": idioma},
            files={"file": (f"fala.{_extensao(tipo)}", audio, tipo)},
        )
        return self._texto_json(resposta)


class VozElevenLabs(_Base):
    nome = "elevenlabs"
    api = "https://api.elevenlabs.io/v1"
    modelo_fala = "eleven_flash_v2_5"
    modelo_transcricao = "scribe_v1"

    async def sintetizar(self, texto: str, voz: str) -> Audio:
        resposta = await self._pedir(
            "POST",
            f"/text-to-speech/{quote(voz, safe='')}?output_format=mp3_44100_64",
            "ao falar",
            headers={"xi-api-key": self._chave},
            json={"text": self._conferir_texto(texto), "model_id": self.modelo_fala},
        )
        return Audio(resposta.content)

    async def transcrever(self, audio: bytes, tipo: str = "audio/webm", idioma: str = "pt") -> str:
        resposta = await self._pedir(
            "POST",
            "/speech-to-text",
            "ao transcrever",
            headers={"xi-api-key": self._chave},
            data={"model_id": self.modelo_transcricao, "language_code": idioma},
            files={"file": (f"fala.{_extensao(tipo)}", audio, tipo)},
        )
        return self._texto_json(resposta)


class VozCartesia(_Base):
    nome = "cartesia"
    api = "https://api.cartesia.ai"
    versao = "2024-06-10"
    modelo_fala = "sonic-3"

    async def sintetizar(self, texto: str, voz: str) -> Audio:
        resposta = await self._pedir(
            "POST",
            "/tts/bytes",
            "ao falar",
            headers={"X-API-Key": self._chave, "Cartesia-Version": self.versao},
            json={
                "model_id": self.modelo_fala,
                "transcript": self._conferir_texto(texto),
                "voice": {"mode": "id", "id": voz},
                "language": "pt",
                "output_format": {"container": "mp3", "sample_rate": 44100, "bit_rate": 128000},
            },
        )
        return Audio(resposta.content)

    async def transcrever(self, audio: bytes, tipo: str = "audio/webm", idioma: str = "pt") -> str:
        resposta = await self._pedir(
            "POST",
            "/stt",
            "ao transcrever",
            headers={"X-API-Key": self._chave, "Cartesia-Version": self.versao},
            data={"model": "ink-whisper", "language": idioma},
            files={"file": (f"fala.{_extensao(tipo)}", audio, tipo)},
        )
        return self._texto_json(resposta)


class VozFish(_Base):
    nome = "fish"
    api = "https://api.fish.audio"
    modelo_fala = "s1"

    def _cabecalhos(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._chave}"}

    async def sintetizar(self, texto: str, voz: str) -> Audio:
        resposta = await self._pedir(
            "POST",
            "/v1/tts",
            "ao falar",
            headers={**self._cabecalhos(), "model": self.modelo_fala, "accept": "audio/mpeg"},
            json={
                "text": self._conferir_texto(texto),
                "reference_id": voz,
                "format": "mp3",
                "mp3_bitrate": 64,
                "latency": "balanced",
                "normalize": True,
            },
        )
        return Audio(resposta.content)

    async def transcrever(self, audio: bytes, tipo: str = "audio/webm", idioma: str = "pt") -> str:
        resposta = await self._pedir(
            "POST",
            "/v1/asr",
            "ao transcrever",
            headers=self._cabecalhos(),
            data={"language": idioma, "ignore_timestamps": "true"},
            files={"audio": (f"fala.{_extensao(tipo)}", audio, tipo)},
        )
        return self._texto_json(resposta)


def obter_voz(nome: str, chave: str, *, cliente: httpx.AsyncClient | None = None) -> ProvedorVoz:
    classes: dict[str, type[_Base]] = {
        "openai": VozOpenAI,
        "elevenlabs": VozElevenLabs,
        "cartesia": VozCartesia,
        "fish": VozFish,
    }
    if nome not in classes:
        raise ErroVoz(f"Provedor de voz desconhecido: {nome!r}.")
    if not chave:
        raise ErroVoz(f"O provedor de voz {nome} precisa de uma chave.")
    return classes[nome](chave, cliente=cliente)  # type: ignore[return-value]
