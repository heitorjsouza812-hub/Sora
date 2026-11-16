"""Nível de raciocínio por modelo: quais níveis cada família aceita e o que vai para o LiteLLM.

O app mostra cinco níveis (``baixo`` … ``maximo``). Cada família de modelo aceita um pedaço deles,
e cada uma recebe o nível de um jeito:

- **gpt-oss e série o da OpenAI** (``o1``, ``o3``, ``o4-mini``) e **gpt-5**: ``reasoning_effort``
  ``low``/``medium``/``high`` → ``baixo``/``medio``/``alto``;
- **Grok 3 mini**: ``reasoning_effort`` ``low``/``high`` → ``baixo``/``alto``;
- **Anthropic com thinking** (Claude 3.7 e da família 4 em diante): orçamento de tokens de
  raciocínio (``thinking.budget_tokens``) por nível; a API exige temperatura 1 e ``max_tokens``
  acima do orçamento;
- **Gemini 2.5 em diante**: orçamento de raciocínio (``thinking_budget``, que o LiteLLM recebe como
  ``thinking.budget_tokens`` e entrega ao Gemini como ``thinkingConfig.thinkingBudget``);
- o resto (Llama, Mistral, DeepSeek, modelos locais…): ``[]``, sem raciocínio ajustável.

A detecção é pelo nome no formato do LiteLLM (``groq/openai/gpt-oss-20b``,
``openrouter/anthropic/claude-sonnet-4``…), porque o catálogo traz modelos mais novos que o mapa
de custos do LiteLLM. Função pura, testada em ``tests/unitarios/test_raciocinio.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

NivelRaciocinio = Literal["baixo", "medio", "alto", "extra_alto", "maximo"]
NIVEIS: tuple[NivelRaciocinio, ...] = ("baixo", "medio", "alto", "extra_alto", "maximo")
AUTO = "auto"

_ESFORCO_OPENAI = {"baixo": "low", "medio": "medium", "alto": "high"}
_ORCAMENTO_ANTHROPIC = {
    "baixo": 1_024,
    "medio": 4_096,
    "alto": 10_000,
    "extra_alto": 20_000,
    "maximo": 32_000,
}
_ORCAMENTO_GEMINI = {
    "baixo": 1_024,
    "medio": 4_096,
    "alto": 8_192,
    "extra_alto": 16_384,
    "maximo": 24_576,
}
_FOLGA_DE_RESPOSTA = 4_096
"""Tokens de resposta acima do orçamento de raciocínio (Anthropic exige ``max_tokens`` maior)."""

_PREFIXO_OPENROUTER = "openrouter/"
_SERIE_O = re.compile(r"(^|/)o\d+(-mini|-pro)?([-:].*)?$")
_GPT5 = re.compile(r"(^|/)gpt-5([.\-].*)?$")
_CLAUDE_VERSAO = re.compile(r"claude-(?:(?:opus|sonnet|haiku|fable)-)?(\d+)(?:[-.](\d+))?")
_GEMINI_VERSAO = re.compile(r"gemini-(\d+)(?:\.(\d+))?")


def _sem_openrouter(modelo: str) -> tuple[str, bool]:
    nome = modelo.strip().lower()
    if nome.startswith(_PREFIXO_OPENROUTER):
        return nome.removeprefix(_PREFIXO_OPENROUTER), True
    return nome, False


def _familia(modelo: str) -> str | None:
    """``esforco3`` · ``esforco2`` · ``anthropic`` · ``gemini`` · ``None``."""
    nome, via_openrouter = _sem_openrouter(modelo)
    if "gpt-oss" in nome:
        return "esforco3"
    ultimo = nome.rsplit("/", 1)[-1]
    if nome.startswith(("openai/", "azure/")) or "/" not in nome or via_openrouter:
        if _SERIE_O.search(ultimo) or _GPT5.search(ultimo):
            return "esforco3"
    if "grok-3-mini" in nome:
        return "esforco2"
    if via_openrouter:
        return None  # thinking da Anthropic e do Gemini não passa igual pelo OpenRouter
    if nome.startswith("anthropic/") or (nome.startswith("claude-") and "/" not in nome):
        achado = _CLAUDE_VERSAO.search(ultimo)
        if achado is None:
            return None
        maior = int(achado.group(1))
        menor = int(achado.group(2)) if achado.group(2) and len(achado.group(2)) <= 2 else 0
        if maior >= 4 or (maior == 3 and menor == 7):
            return "anthropic"
        return None
    if nome.startswith(("gemini/", "vertex_ai/")):
        achado = _GEMINI_VERSAO.search(ultimo)
        if achado is None:
            return None
        maior = int(achado.group(1))
        menor = int(achado.group(2) or 0)
        if (maior, menor) >= (2, 5) and "image" not in ultimo and "embedding" not in ultimo:
            return "gemini"
    return None


def niveis_de_raciocinio(modelo: str) -> list[NivelRaciocinio]:
    """Níveis que o modelo aceita, na ordem; ``[]`` = sem raciocínio ajustável."""
    familia = _familia(modelo)
    if familia == "esforco3":
        return ["baixo", "medio", "alto"]
    if familia == "esforco2":
        return ["baixo", "alto"]
    if familia in {"anthropic", "gemini"}:
        return list(NIVEIS)
    return []


def nivel_mais_proximo(modelo: str, nivel: str) -> NivelRaciocinio | None:
    """No automático o nível escolhido vale para o modelo que o seletor achar: se ele não aceita
    exatamente esse nível, usa o aceito mais perto (``maximo`` no gpt-oss vira ``alto``).
    ``None`` quando o modelo não tem raciocínio ajustável ou o nível é ``auto``."""
    aceitos = niveis_de_raciocinio(modelo)
    if not aceitos or nivel not in NIVEIS:
        return None
    if nivel in aceitos:
        return nivel  # type: ignore[return-value]
    alvo = NIVEIS.index(nivel)  # type: ignore[arg-type]
    return min(aceitos, key=lambda n: (abs(NIVEIS.index(n) - alvo), -NIVEIS.index(n)))


@dataclass(frozen=True, slots=True)
class ParametrosRaciocinio:
    """O que muda na criação do ``ChatLiteLLM`` para um nível de raciocínio."""

    extras: dict[str, Any] = field(default_factory=dict)
    """Vai em ``model_kwargs`` (o LiteLLM traduz para cada provedor)."""
    temperatura: float | None = None
    """Temperatura obrigatória (Anthropic com thinking só aceita 1)."""
    max_tokens_minimo: int | None = None
    """``max_tokens`` mínimo para caber o raciocínio e a resposta."""


def parametros_de_raciocinio(modelo: str, nivel: str) -> ParametrosRaciocinio | None:
    """Parâmetros do LiteLLM para o nível. ``None`` = nada a mudar (``auto``, nível que o modelo
    não aceita ou modelo sem raciocínio ajustável)."""
    if nivel not in niveis_de_raciocinio(modelo):
        return None
    familia = _familia(modelo)
    if familia in {"esforco3", "esforco2"}:
        return ParametrosRaciocinio(extras={"reasoning_effort": _ESFORCO_OPENAI[nivel]})
    if familia == "anthropic":
        orcamento = _ORCAMENTO_ANTHROPIC[nivel]
        return ParametrosRaciocinio(
            extras={"thinking": {"type": "enabled", "budget_tokens": orcamento}},
            temperatura=1.0,
            max_tokens_minimo=orcamento + _FOLGA_DE_RESPOSTA,
        )
    if familia == "gemini":
        return ParametrosRaciocinio(
            extras={"thinking": {"type": "enabled", "budget_tokens": _ORCAMENTO_GEMINI[nivel]}}
        )
    return None


def e_rapido(nivel: str, velocidade_tps: int | None) -> bool:
    """Modelo indicado para resposta rápida: N1 ou que gera 300 tokens por segundo ou mais."""
    return nivel == "N1" or (velocidade_tps or 0) >= 300
