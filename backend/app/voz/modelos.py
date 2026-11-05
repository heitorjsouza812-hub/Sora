"""Escolha dos modelos de voz de um provedor compatível com a OpenAI (Groq, etc.).

A OpenAI de verdade mantém os modelos fixos de ``VozOpenAI``. Num provedor compatível o modelo vem
da lista que ele mesmo publica: transcrição = o que tem ``whisper`` ou ``transcribe`` no nome;
fala = ``tts``, ``speech``, ``orpheus`` ou ``playai``.
"""

from __future__ import annotations

from collections.abc import Iterable

TRANSCRICAO_FALLBACK = "whisper-1"  # lista indisponível: o nome mais comum nesses provedores
FALA_FALLBACK = "gpt-4o-mini-tts"

_MARCAS_TRANSCRICAO = ("transcribe", "whisper")
_MARCAS_FALA = ("tts", "speech", "orpheus", "playai")


def _limpar(nome: str) -> str:
    return nome.split("/", 1)[1] if nome.startswith("openai/") else nome


def _escolher(nomes: Iterable[str], marcas: tuple[str, ...]) -> str | None:
    achados = sorted(
        {_limpar(n) for n in nomes if any(m in n.lower() for m in marcas)},
        # "distil" e "guard" ficam por último; entre os demais, a ordem das marcas decide.
        key=lambda n: (
            "distil" in n.lower() or "guard" in n.lower(),
            min(i for i, m in enumerate(marcas) if m in n.lower()),
            n,
        ),
    )
    return achados[0] if achados else None


def modelo_de_transcricao(nomes: Iterable[str]) -> str | None:
    return _escolher(nomes, _MARCAS_TRANSCRICAO)


def modelo_de_fala(nomes: Iterable[str]) -> str | None:
    return _escolher(nomes, _MARCAS_FALA)
