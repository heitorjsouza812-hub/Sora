"""Saída estruturada compatível com o modo estrito dos provedores (Groq, OpenAI).

O ``ChatLiteLLM.with_structured_output`` manda ``response_format = json_schema`` com
``strict: true`` e só acrescenta ``additionalProperties: false``. No modo estrito o provedor
também exige:

- ``required`` com **todas** as chaves de ``properties`` (campo opcional = aceita ``null``);
- nada de ``default``, limites (``maxLength``, ``maxItems``, ``minimum``…), ``pattern`` nem
  ``format`` (a Groq recusa; a conferência dos limites fica no código).

``violacoes_modo_estrito`` diz o que quebra essas regras (os testes passam por ele cada esquema
usado com saída estruturada). ``com_saida_estruturada`` tenta o modo estrito e, se o provedor
recusar o pedido (``400``), cai para ``json_object`` com o esquema no prompt.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from pydantic import BaseModel

_PROIBIDAS = frozenset(
    {
        "default", "format", "pattern", "minLength", "maxLength", "minItems", "maxItems",
        "uniqueItems", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
        "multipleOf", "minProperties", "maxProperties", "patternProperties",
    }
)  # fmt: skip


def _fechar_objetos(no: Any) -> None:
    """O mesmo que o ``langchain-litellm`` faz antes de mandar: ``additionalProperties: false``."""
    if isinstance(no, dict):
        if no.get("type") == "object" or "properties" in no:
            no["additionalProperties"] = False
        for valor in no.values():
            _fechar_objetos(valor)
    elif isinstance(no, list):
        for item in no:
            _fechar_objetos(item)


def esquema_enviado(esquema: type[BaseModel]) -> dict[str, Any]:
    """O JSON schema que vai em ``response_format`` (como o ``ChatLiteLLM`` monta)."""
    from langchain_core.utils.function_calling import convert_to_openai_tool

    parametros = copy.deepcopy(convert_to_openai_tool(esquema)["function"]["parameters"])
    _fechar_objetos(parametros)
    return parametros


def violacoes_modo_estrito(no: Any, caminho: str = "#") -> list[str]:
    """Lista as regras do modo estrito que o esquema quebra (vazia = compatível)."""
    erros: list[str] = []
    if isinstance(no, dict):
        for chave in sorted(_PROIBIDAS & no.keys()):
            # "default" dentro de properties é o nome de um campo, não a palavra-chave
            if not caminho.endswith("/properties"):
                erros.append(f"{caminho}: '{chave}' não é aceito no modo estrito")
        if no.get("type") == "object" or (
            "properties" in no and not caminho.endswith("/properties")
        ):
            propriedades = set((no.get("properties") or {}).keys())
            if set(no.get("required") or []) != propriedades:
                erros.append(
                    f"{caminho}: required precisa ter todas as chaves {sorted(propriedades)}"
                )
            if no.get("additionalProperties") is not False:
                erros.append(f"{caminho}: additionalProperties precisa ser false")
        for chave, valor in no.items():
            erros.extend(violacoes_modo_estrito(valor, f"{caminho}/{chave}"))
    elif isinstance(no, list):
        for i, item in enumerate(no):
            erros.extend(violacoes_modo_estrito(item, f"{caminho}/{i}"))
    return erros


def instrucoes_json(esquema: type[BaseModel]) -> str:
    """Texto para o prompt: serve ao modo estrito e é o que guia a queda em ``json_object``."""
    return (
        "Responda só com um objeto JSON neste esquema (todas as chaves; use null quando não "
        "se aplica):\n" + json.dumps(esquema_enviado(esquema), ensure_ascii=False)
    )


def _erros_de_pedido() -> tuple[type[BaseException], ...]:
    try:
        import litellm
    except ImportError:  # pragma: no cover - litellm é dependência do backend
        return ()
    return tuple(
        erro
        for erro in (
            getattr(litellm, "BadRequestError", None),
            getattr(litellm, "UnsupportedParamsError", None),
        )
        if isinstance(erro, type)
    )


def com_saida_estruturada(modelo: Any, esquema: type[BaseModel]) -> Any:
    """Runnable que devolve ``esquema`` preenchido: estrito primeiro, ``json_object`` na queda.

    A queda só acontece quando o provedor recusa o pedido (400 / parâmetro sem suporte); erro
    de rede, limite ou chave segue como erro. O prompt precisa trazer ``instrucoes_json``
    (o modo ``json_object`` não recebe o esquema)."""
    estrito = modelo.with_structured_output(esquema, method="json_schema", strict=True)
    erros = _erros_de_pedido()
    if not erros or not hasattr(estrito, "with_fallbacks"):
        return estrito
    queda = modelo.with_structured_output(esquema, method="json_mode")
    return estrito.with_fallbacks([queda], exceptions_to_handle=erros)
