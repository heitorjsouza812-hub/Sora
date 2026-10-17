"""Redação de segredos em textos, erros e payloads de ferramentas.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``connector-safety.ts``,
``core/events.ts`` (``redactSecrets``) e ``pi-runtime.ts`` (``sanitizeSensitiveText`` e
``redactActivityUrl``). Veja ``docs/referencias/rakazo.md``.

Duas camadas:

- ``redigir_segredos``: troca segredos **conhecidos** (as chaves do usuário que o worker
  decifrou para esta execução) por ``[oculto]``;
- ``limpar_texto_sensivel``: troca padrões que parecem segredo mesmo sem conhecê-los
  (``sk-…``, ``Bearer …``, JWT, ``api_key=…``).

Tudo que vai para o modelo, para os logs ou para o app como erro de ferramenta passa
pelas duas.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

OCULTO = "[oculto]"
LIMITE_ERRO_CARACTERES = 2_000

_PADROES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-or-v1-[A-Za-z0-9]+"), OCULTO),
    (re.compile(r"sk-(?:ant-|proj-)?[A-Za-z0-9_-]{8,}"), OCULTO),
    (re.compile(r"gsk_[A-Za-z0-9]{8,}"), OCULTO),  # Groq
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), OCULTO),  # Google
    (re.compile(r"xai-[A-Za-z0-9]{8,}"), OCULTO),
    (re.compile(r"(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{10,}"), OCULTO),
    (re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}"), OCULTO),  # token de bot do Telegram
    (re.compile(r"Bearer\s+[^\s\"',;&]+", re.IGNORECASE), f"Bearer {OCULTO}"),
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), OCULTO),
    (
        re.compile(
            r"((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|senha|secret|segredo|"
            r"token|chave)\s*[=:]\s*)[^\s\"',;&]+",
            re.IGNORECASE,
        ),
        rf"\1{OCULTO}",
    ),
    (
        re.compile(r"((?:auth|authorization)\s*[=:]\s*)(?!Bearer\b)[^\s\"',;&]+", re.IGNORECASE),
        rf"\1{OCULTO}",
    ),
)

CHAVES_SENSIVEIS = re.compile(
    r"password|senha|secret|segredo|token|api[_-]?key|chave|authorization|cookie|credential|"
    r"credencial",
    re.IGNORECASE,
)
"""Nomes de argumento cujo valor nunca aparece em passo, log ou revisor."""


def _ativos(segredos: Iterable[str]) -> list[str]:
    # Mais longos primeiro: um segredo que contém outro some inteiro.
    return sorted({s for s in segredos if s and len(s) >= 4}, key=len, reverse=True)


def redigir_segredos(texto: str, segredos: Iterable[str]) -> str:
    """Troca cada segredo conhecido por ``[oculto]``."""
    for segredo in _ativos(segredos):
        texto = texto.replace(segredo, OCULTO)
    return texto


def contem_segredo(valor: Any, segredos: Iterable[str]) -> bool:
    """O valor (texto, número, lista, dicionário, inclusive chaves) contém um segredo conhecido."""
    ativos = _ativos(segredos)
    if not ativos:
        return False
    pendentes: list[Any] = [valor]
    while pendentes:
        atual = pendentes.pop()
        if isinstance(atual, dict):
            for chave, item in atual.items():
                pendentes.extend((str(chave), item))
        elif isinstance(atual, list | tuple | set):
            pendentes.extend(atual)
        elif atual is not None:
            texto = str(atual)
            if any(segredo in texto for segredo in ativos):
                return True
    return False


def limpar_texto_sensivel(texto: str) -> str:
    """Troca padrões com cara de segredo, mesmo sem conhecer o valor."""
    for padrao, troca in _PADROES:
        texto = padrao.sub(troca, texto)
    return texto


def redigir(texto: str, segredos: Iterable[str] = ()) -> str:
    """As duas camadas juntas: segredos conhecidos e padrões."""
    return limpar_texto_sensivel(redigir_segredos(texto, segredos))


def redigir_payload(valor: Any, segredos: Iterable[str]) -> Any:
    """Copia o payload trocando segredos conhecidos em textos, números e chaves.

    Número ou booleano que contém um segredo vira ``"[oculto]"`` inteiro (não dá para
    cortar um pedaço de um número). Objeto que não vira JSON é trocado por ``{"ok": true}``.
    """
    ativos = _ativos(segredos)
    if not ativos:
        return valor
    try:
        copia = json.loads(json.dumps(valor, default=str))
    except (TypeError, ValueError):
        return {"ok": True}
    return _redigir_valor(copia, ativos)


def _redigir_valor(valor: Any, ativos: list[str]) -> Any:
    if isinstance(valor, str):
        return redigir_segredos(valor, ativos)
    if isinstance(valor, list):
        return [_redigir_valor(item, ativos) for item in valor]
    if isinstance(valor, dict):
        return {
            redigir_segredos(str(chave), ativos): _redigir_valor(item, ativos)
            for chave, item in valor.items()
        }
    if valor is None:
        return None
    texto = json.dumps(valor)
    return OCULTO if redigir_segredos(texto, ativos) != texto else valor


def ocultar_argumentos_sensiveis(argumentos: dict[str, Any]) -> dict[str, Any]:
    """Troca o valor de argumentos com nome sensível (``senha``, ``api_key``…) por ``[oculto]``,
    em qualquer nível, e limpa padrões de segredo nos textos."""

    def limpar(valor: Any) -> Any:
        if isinstance(valor, dict):
            return {
                chave: OCULTO if CHAVES_SENSIVEIS.search(str(chave)) else limpar(item)
                for chave, item in valor.items()
            }
        if isinstance(valor, list):
            return [limpar(item) for item in valor]
        if isinstance(valor, str):
            return limpar_texto_sensivel(valor)
        return valor

    return limpar(argumentos)


def sanitizar_erro(erro: BaseException | str, segredos: Iterable[str] = ()) -> str:
    """Mensagem de erro segura para devolver ao modelo ou ao app (máx. 2.000 caracteres)."""
    mensagem = str(erro) if isinstance(erro, str) else (str(erro) or type(erro).__name__)
    return redigir(mensagem, segredos)[:LIMITE_ERRO_CARACTERES]


def url_sem_segredos(url: str) -> str:
    """Só origem e caminho: tira usuário, senha, query e fragmento.

    Entrada que não é URL vira ``"[url inválida]"``: nunca ecoa texto que pode ter segredo.
    """
    bruto = str(url or "").strip()
    if not bruto:
        return bruto
    try:
        partes = urlsplit(bruto)
    except ValueError:
        return "[url inválida]"
    if not partes.scheme or not partes.hostname:
        return "[url inválida]"
    host = partes.hostname
    if partes.port:
        host = f"{host}:{partes.port}"
    return urlunsplit((partes.scheme, host, partes.path, "", ""))
