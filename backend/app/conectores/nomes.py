"""Nomes de ferramenta que todos os provedores aceitam (``^[a-zA-Z0-9_-]{1,64}$``).

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``normalizeAgentToolName``,
``normalizeAgentToolNames`` e ``toAgentTools`` em ``adapters/src/pi-runtime.ts``.

O nome mostrado ao modelo é ``mcp__<servidor>__<ferramenta>`` (dois sublinhados: a
Anthropic recusa ``mcp_`` com um só em alguns endpoints). A execução sempre usa o nome
original guardado no embrulho; só o nome visível muda.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

MAX_NOME = 64
NOME_PADRAO = "ferramenta"
_SEGURO = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def nome_seguro(nome: str) -> bool:
    return bool(_SEGURO.match(nome))


def normalizar(nome: str, limite: int = MAX_NOME) -> str:
    """Tira acentos e troca o resto por ``_``: ``Criar Página!`` → ``Criar_Pagina``."""
    if nome_seguro(nome) and len(nome) <= limite:
        return nome
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c)
    )
    limpo = re.sub(r"[^a-zA-Z0-9_-]+", "_", sem_acento).strip("_")
    return (limpo or NOME_PADRAO)[:limite]


def slug_servidor(nome: str) -> str:
    """Nome do servidor como vai no prefixo: minúsculo, sem ``__`` (que separa as partes)."""
    slug = normalizar(nome.lower(), 24).replace("__", "_").strip("_-")
    return slug or "servidor"


def nome_conector(servidor: str, ferramenta: str) -> str:
    """``mcp__notion__buscar_paginas``, cortando a ferramenta para caber em 64 caracteres."""
    prefixo = f"mcp__{slug_servidor(servidor)}__"
    return prefixo + normalizar(ferramenta, MAX_NOME - len(prefixo))


def nomes_unicos(nomes: Sequence[str]) -> list[str]:
    """Um nome válido e único por ferramenta, na mesma ordem.

    Nomes já válidos são reservados primeiro, então normalizar um nome nunca toma o lugar
    de outro que já era válido. Colisões ganham ``_2``, ``_3``…
    """
    reservados = {n for n in nomes if nome_seguro(n)}
    usados: set[str] = set()
    saida: list[str] = []
    for original in nomes:
        base = (
            original if nome_seguro(original) and original not in usados else normalizar(original)
        )
        candidato = base
        contador = 2
        while candidato in usados or (candidato != original and candidato in reservados):
            sufixo = f"_{contador}"
            candidato = base[: MAX_NOME - len(sufixo)] + sufixo
            contador += 1
        usados.add(candidato)
        saida.append(candidato)
    return saida
