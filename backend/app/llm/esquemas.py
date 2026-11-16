"""Esquemas de ferramenta e histórico no formato que cada provedor aceita (Engrenagem).

**Gemini** (``gemini/…``, ``vertex_ai/…``): o LiteLLM já tira ``$ref``, ``additionalProperties``
e campos fora do ``Schema`` do Google, mas deixa passar ``{"type": "object"}`` sem
``properties``, que o Gemini recusa ("properties: should be non-empty for OBJECT type"). É o caso
de ``conectores_executar_ferramenta.argumentos`` (vai em todo turno da Sora e dos bots), de
``entregar.conteudo`` e de ``navegador_lote``. Para o Gemini esse campo vira texto com JSON
dentro, e a ferramenta sem parâmetro vai sem ``parameters``.

**Argumentos em texto**: o caminho de volta. Se o modelo manda um JSON em texto num campo que o
esquema pede objeto ou lista (o Gemini depois do ajuste acima, e modelos pequenos da Groq às
vezes por conta própria), o texto é lido antes da validação.

**Histórico**: chamada de ferramenta sem resposta (turno interrompido, erro, Parar) ou resposta
sem a chamada dela fazem OpenAI, Anthropic e Groq responderem 400. ``historico_valido`` devolve a
lista com uma resposta "interrompida" para cada chamada órfã e sem as respostas soltas.
"""

from __future__ import annotations

import copy
import json
from typing import Any

PREFIXOS_GEMINI = ("gemini/", "vertex_ai/", "vertex_ai_beta/")

DESCRICAO_JSON = "Objeto JSON escrito como texto."

RESPOSTA_INTERROMPIDA = "Sem resultado: esta chamada foi interrompida antes de terminar."


def modelo_gemini(nome: str | None) -> bool:
    return str(nome or "").strip().lower().startswith(PREFIXOS_GEMINI)


def _aberto(esquema: Any) -> bool:
    """Objeto sem propriedades ou esquema vazio (``{}``, "qualquer coisa")."""
    if not isinstance(esquema, dict):
        return False
    if esquema.get("type") == "object":
        return not esquema.get("properties")
    return not any(chave in esquema for chave in ("type", "anyOf", "oneOf", "allOf", "enum"))


def _texto_json(descricao: Any = "") -> dict[str, Any]:
    descricao = str(descricao or "").strip()
    return {
        "type": "string",
        "description": f"{descricao} ({DESCRICAO_JSON})" if descricao else DESCRICAO_JSON,
    }


def _sanear_gemini(esquema: Any) -> Any:
    """Um nó de esquema (nunca o mapa ``properties``) sem objeto aberto."""
    if not isinstance(esquema, dict):
        return esquema
    if _aberto(esquema):
        return _texto_json(esquema.get("description"))
    novo = dict(esquema)
    if isinstance(esquema.get("properties"), dict):
        novo["properties"] = {
            nome: _sanear_gemini(valor) for nome, valor in esquema["properties"].items()
        }
    if isinstance(esquema.get("items"), dict):
        novo["items"] = _sanear_gemini(esquema["items"])
    for chave in ("anyOf", "oneOf"):
        variantes = esquema.get(chave)
        if not isinstance(variantes, list):
            continue
        convertidas = [_sanear_gemini(v) for v in variantes]
        # Se o campo já aceita texto, a variante "JSON em texto" é redundante.
        if any(isinstance(v, dict) and v.get("type") == "string" for v in variantes):
            convertidas = [
                v
                for v, original in zip(convertidas, variantes, strict=True)
                if not (
                    isinstance(original, dict)
                    and (
                        _aberto(original)
                        or (original.get("type") == "array" and _aberto(original.get("items")))
                    )
                )
            ] or convertidas
        unicas: list[Any] = []
        for variante in convertidas:
            if variante not in unicas:
                unicas.append(variante)
        novo[chave] = unicas
    return novo


def ferramenta_para_gemini(ferramenta: dict[str, Any]) -> dict[str, Any]:
    """Ferramenta no formato OpenAI (``convert_to_openai_tool``) ajustada para o Gemini."""
    nova = copy.deepcopy(ferramenta)
    funcao = nova.get("function")
    if not isinstance(funcao, dict):
        return nova
    parametros = funcao.get("parameters")
    if not isinstance(parametros, dict):
        return nova
    if not parametros.get("properties"):
        funcao.pop("parameters", None)  # ferramenta sem parâmetro: o Gemini quer sem o campo
        return nova
    raiz = dict(parametros)
    raiz["properties"] = {
        nome: _sanear_gemini(valor) for nome, valor in parametros["properties"].items()
    }
    funcao["parameters"] = raiz
    return nova


# ---------- argumentos em texto ----------


def _aceita(esquema: dict[str, Any], tipo: str) -> bool:
    tipos = esquema.get("type")
    if tipos == tipo or (isinstance(tipos, list) and tipo in tipos):
        return True
    return any(
        isinstance(v, dict) and _aceita(v, tipo)
        for chave in ("anyOf", "oneOf")
        for v in esquema.get(chave) or []
    )


def _ler(regra: Any, valor: Any) -> Any:
    if not isinstance(regra, dict):
        return valor
    if isinstance(valor, str) and not _aceita(regra, "string"):
        for tipo, classe in (("object", dict), ("array", list)):
            if _aceita(regra, tipo):
                try:
                    lido = json.loads(valor)
                except ValueError:
                    return valor  # a validação devolve o erro ao modelo
                return _ler(regra, lido) if isinstance(lido, classe) else valor
        return valor
    if isinstance(valor, dict) and isinstance(regra.get("properties"), dict):
        return argumentos_lidos(regra, valor)
    if isinstance(valor, list) and isinstance(regra.get("items"), dict):
        return [_ler(regra["items"], item) for item in valor]
    return valor


def argumentos_lidos(esquema: dict[str, Any], argumentos: Any) -> Any:
    """Lê o JSON em texto dos campos que pedem objeto ou lista e não aceitam texto (também
    dentro de objetos e listas)."""
    if not isinstance(argumentos, dict) or not isinstance(esquema, dict):
        return argumentos
    propriedades = esquema.get("properties") or {}
    return {nome: _ler(propriedades.get(nome), valor) for nome, valor in argumentos.items()}


# ---------- histórico ----------


def historico_valido(mensagens: list[Any]) -> list[Any]:
    """Cópia da lista em que cada chamada de ferramenta tem a resposta logo depois dela (a
    resposta que veio fora do lugar sobe; a que falta vira "interrompida") e nenhuma resposta fica
    solta. Sem nada a consertar, devolve a mesma lista."""
    from langchain_core.messages import AIMessage, ToolMessage

    saida: list[Any] = []
    indice = 0
    while indice < len(mensagens):
        mensagem = mensagens[indice]
        indice += 1
        if isinstance(mensagem, ToolMessage):
            continue  # resposta sem a chamada (a chamada consome as dela abaixo)
        saida.append(mensagem)
        if not (isinstance(mensagem, AIMessage) and mensagem.tool_calls):
            continue
        # Trecho até a próxima resposta do modelo: as respostas desta chamada e o resto.
        fim = indice
        while fim < len(mensagens) and not isinstance(mensagens[fim], AIMessage):
            fim += 1
        trecho = mensagens[indice:fim]
        indice = fim
        respostas: dict[str, Any] = {}
        outras: list[Any] = []
        for item in trecho:
            if isinstance(item, ToolMessage):
                if item.tool_call_id not in respostas:
                    respostas[item.tool_call_id] = item
            else:
                outras.append(item)
        for chamada in mensagem.tool_calls:
            identificador = str(chamada.get("id"))
            saida.append(
                respostas.get(identificador)
                or ToolMessage(
                    content=RESPOSTA_INTERROMPIDA,
                    tool_call_id=identificador,
                    name=str(chamada.get("name") or ""),
                    status="error",
                )
            )
        saida.extend(outras)
    if len(saida) == len(mensagens) and all(a is b for a, b in zip(saida, mensagens, strict=True)):
        return mensagens
    return saida
