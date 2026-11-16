"""Filtro do seletor e destaques editoriais; modelos de outras funções seguem no banco."""

import re
from collections import defaultdict

_NAO_CHAT = re.compile(
    r"embed|whisper|tts|orpheus|transcrib|speech|audio|realtime|moderation|guard|safeguard|"
    r"imagen|dall-e|image|veo|aqa|rerank|text-search|text-similarity|live|computer-use",
    re.IGNORECASE,
)
_CURADOS = {
    "openai": ("gpt-5", "gpt-4.1", "gpt-4o", "o3"),
    "anthropic": ("claude-opus-4", "claude-sonnet-4", "claude-haiku-4", "claude-3-7-sonnet"),
    "gemini": ("gemini-3", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"),
    "groq": ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b", "llama-3.1-8b"),
}


def modelo_de_chat(modelo: str) -> bool:
    return not bool(_NAO_CHAT.search(modelo))


def modelos_principais(modelos: list[str]) -> set[str]:
    """Até quatro modelos por prefixo; uma variante por família curada, senão primeiros chats."""
    grupos: dict[str, list[str]] = defaultdict(list)
    for nome in sorted(set(modelos)):
        if modelo_de_chat(nome):
            grupos[nome.split("/", 1)[0]].append(nome)
    resultado: set[str] = set()
    for provedor, nomes in grupos.items():
        escolhidos = []
        for familia in _CURADOS.get(provedor, ()):
            candidatos = [n for n in nomes if n.split("/", 1)[-1].startswith(familia)]
            if candidatos:
                escolhidos.append(min(candidatos, key=lambda n: (len(n), n)))
        resultado.update(escolhidos or nomes[:4])
    return resultado
