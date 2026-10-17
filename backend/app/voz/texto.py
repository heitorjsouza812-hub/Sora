"""Texto do agente → frase que uma voz consegue ler.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``core/src/speech-text.ts``
(``speakable``, ``toUtterances``, ``splitLong``), traduzido para PT-BR.

Fala a prosa, dá nome aos artefatos e joga fora a sintaxe: bloco de código vira "(um bloco
de código em Python)", link vira "um link", tabela vira uma linha por item, emoji some.
"""

from __future__ import annotations

import re

_LINGUAGENS = {
    "ts": "TypeScript",
    "tsx": "TypeScript",
    "js": "JavaScript",
    "jsx": "JavaScript",
    "py": "Python",
    "python": "Python",
    "sh": "shell",
    "bash": "shell",
    "json": "JSON",
    "yml": "YAML",
    "yaml": "YAML",
    "sql": "SQL",
    "rs": "Rust",
    "go": "Go",
    "html": "HTML",
    "css": "CSS",
    "diff": "diff",
}
_TERMINA_FRASE = re.compile(r"[.!?:;]\s*$")
_EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿︀-️←-⇿⬀-⯿]")
_FRONTEIRA = re.compile(
    r"(?<!\bex)(?<!\betc)(?<!\bSr)(?<!\bSra)(?<!\bDr)(?<!\bDra)(?<![.\d])([.!?])([\"')\]]*)\s+"
)


def _bloco(cerca: str) -> str:
    linguagem = re.sub(r"[^a-z0-9+#]", "", (cerca.strip().split() or [""])[0].lower())
    nome = _LINGUAGENS.get(linguagem)
    return f". (um bloco de código em {nome}) " if nome else ". (um bloco de código) "


def falavel(entrada: str) -> str:
    """Markdown (ou qualquer saída de agente) → uma linha para a voz ler."""
    if not entrada:
        return ""
    texto = re.sub(r"```([^\n]*)\n[\s\S]*?(?:```|$)", lambda m: _bloco(m.group(1)), entrada)
    texto = re.sub(r"~~~([^\n]*)\n[\s\S]*?(?:~~~|$)", lambda m: _bloco(m.group(1)), texto)
    texto = re.sub(
        r"!\[([^\]]*)\]\([^)]*\)",
        lambda m: f". (imagem: {m.group(1)}) " if m.group(1) else ". (uma imagem) ",
        texto,
    )
    texto = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", texto)
    texto = re.sub(r"<https?://[^>\s]+>", " um link ", texto)
    texto = re.sub(r"\bhttps?://\S+", " um link ", texto)
    texto = re.sub(r"^\s*\|?[\s:-]*\|[\s|:-]*$", "", texto, flags=re.MULTILINE)
    texto = re.sub(
        r"^\s*\|(.+)\|\s*$",
        lambda m: ", ".join(c.strip() for c in m.group(1).split("|") if c.strip()),
        texto,
        flags=re.MULTILINE,
    )
    texto = re.sub(
        r"`([^`\n]+)`", lambda m: m.group(1) if len(m.group(1)) <= 40 else " esse trecho ", texto
    )
    texto = re.sub(
        r"^\s{0,3}#{1,6}\s+(.*)$",
        lambda m: m.group(1) if _TERMINA_FRASE.search(m.group(1)) else f"{m.group(1).strip()}.",
        texto,
        flags=re.MULTILINE,
    )
    texto = re.sub(r"^\s*[-*+]\s+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^\s*\d+[.)]\s+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^\s*>\s?", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^\s*(?:[-*_]\s*){3,}$", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"(\*\*|__)(.*?)\1", r"\2", texto)
    texto = re.sub(r"(\*|_)(?=\S)(.*?)(?<=\S)\1", r"\2", texto)
    texto = re.sub(r"~~(.*?)~~", r"\1", texto)
    texto = re.sub(r"\[[ xX]\]\s*", "", texto)
    texto = re.sub(r"(?:[\w.@-]+/)+([\w.-]+\.\w{1,6})\b", r"\1", texto)  # pastas são para o olho
    texto = _EMOJI.sub("", texto)
    texto = re.sub(r"\n{2,}", ". ", texto).replace("\n", ". ")
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"\s+([.,!?;:])", r"\1", texto)
    texto = re.sub(r"(?:\.\s*){2,}", ". ", texto)
    texto = re.sub(r",\s*\.", ".", texto).strip()
    return texto if re.search(r"\w", texto) else ""


def _dividir_longo(texto: str, maximo: int) -> list[str]:
    saida: list[str] = []
    resto = texto
    while len(resto) > maximo:
        janela = resto[:maximo]
        posicao = max(janela.rfind(", "), janela.rfind("; "), janela.rfind(" — "))
        corte = posicao + 1 if posicao > maximo / 2 else janela.rfind(" ")
        if corte <= 0:
            break
        saida.append(resto[:corte].strip())
        resto = resto[corte:].strip()
    if resto:
        saida.append(resto)
    return saida


def frases(entrada: str, *, minimo: int = 12, maximo: int = 320) -> list[str]:
    """Divide em falas que o sintetizador pode começar logo; pedaços curtos colam no vizinho."""
    texto = falavel(entrada)
    if not texto:
        return []
    marca = "\u0000"
    brutas = [p.strip() for p in _FRONTEIRA.sub(rf"\1\2{marca}", texto).split(marca) if p.strip()]
    saida: list[str] = []
    for pedaco in brutas:
        for parte in [pedaco] if len(pedaco) <= maximo else _dividir_longo(pedaco, maximo):
            if saida and (len(saida[-1]) < minimo or len(parte) < minimo):
                saida[-1] = f"{saida[-1]} {parte}"
            else:
                saida.append(parte)
    return saida
