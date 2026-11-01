"""Rastro das chamadas do navegador por árvore (para o painel Trabalho e para depurar).

Cada chamada vira um evento: momento, comando, argumentos (redigidos), ``ok``, código de erro,
entrega e duração. O texto digitado num campo de senha nunca entra; o resto passa pela
redação de segredos da Sora (``app/core/redacao.py``). O rastro só cresce (eventos novos no
fim) e guarda os últimos ``MAX_EVENTOS``; ``jsonl()`` exporta uma linha por evento.

Ideia do agent-desktop (github.com/vercel-labs/agent-desktop, Apache-2.0): "trace segments"
JSONL com esquema que só ganha campos. Aqui fica em memória, por aba.
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app.core.redacao import OCULTO, limpar_texto_sensivel

ESQUEMA = 1
MAX_EVENTOS = 500
_CAMPOS_DE_TEXTO = frozenset({"texto", "opcao", "valor"})


def redigir_argumentos(args: dict[str, Any], *, senha: bool = False) -> dict[str, Any]:
    saida: dict[str, Any] = {}
    for chave, valor in args.items():
        if valor is None:
            continue
        if chave in _CAMPOS_DE_TEXTO and isinstance(valor, str):
            saida[chave] = OCULTO if senha else limpar_texto_sensivel(valor)[:200]
        elif isinstance(valor, str):
            saida[chave] = limpar_texto_sensivel(valor)[:200]
        else:
            saida[chave] = valor
    return saida


@dataclass(slots=True)
class Rastro:
    eventos: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=MAX_EVENTOS))

    def anotar(
        self,
        comando: str,
        args: dict[str, Any],
        *,
        ok: bool,
        codigo: str | None,
        entrega: str | None,
        inicio: float,
        senha: bool = False,
    ) -> dict[str, Any]:
        evento: dict[str, Any] = {
            "esquema": ESQUEMA,
            "momento_ms": int(time.time() * 1000),
            "comando": comando,
            "args": redigir_argumentos(args, senha=senha),
            "ok": ok,
            "duracao_ms": int((time.monotonic() - inicio) * 1000),
        }
        if codigo:
            evento["codigo"] = codigo
        if entrega:
            evento["entrega"] = entrega
        self.eventos.append(evento)
        return evento

    def jsonl(self) -> str:
        return "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self.eventos)
