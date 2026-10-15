"""Saída JSON do Sistema 1: validar, consertar uma vez, escalar para o N2.

Especificação: prompts 03 ("Se o JSON vier inválido, o backend tenta consertar uma vez e, se
falhar, manda o pedido para o N2"), §6.1 (``ToolErrorMiddleware`` / ``handle_errors`` na saída
estruturada) e §5 (meta: JSON válido de primeira em 99%).

Este módulo faz o conserto "de graça", sem chamar modelo: tira texto solto e cercas de código,
fecha o que ficou aberto e arruma vírgula sobrando, aspas curvas/simples e ``True``/``None``.
O conserto por modelo (pedir de novo com o erro) e a escalada para o N2 ficam em ``triagem.py``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.sistema1.esquemas import SaidaSistema1

_BLOCO_DE_RACIOCINIO = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CERCA_DE_CODIGO = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
_ASPAS_E_FECHAMENTO = {
    '"': '"',
    chr(0x201C): chr(0x201D),  # aspas duplas curvas
    chr(0x201D): chr(0x201D),
    "'": "'",
    chr(0x2018): chr(0x2019),  # aspas simples curvas
    chr(0x2019): chr(0x2019),
}
_LITERAIS_DE_PYTHON = {"True": "true", "False": "false", "None": "null"}


class SaidaInvalida(Exception):
    """O JSON não passou na validação nem depois do conserto."""

    def __init__(self, texto_bruto: str, erros: str) -> None:
        super().__init__(erros)
        self.texto_bruto = texto_bruto
        self.erros = erros


def _primeiro_objeto(texto: str) -> str | None:
    """Do primeiro ``{`` até o ``}`` que o fecha; se faltar o fecho, até o fim do texto."""
    inicio = texto.find("{")
    if inicio < 0:
        return None
    profundidade, em_texto, escapado = 0, False, False
    for posicao in range(inicio, len(texto)):
        c = texto[posicao]
        if em_texto:
            if escapado:
                escapado = False
            elif c == "\\":
                escapado = True
            elif c == '"':
                em_texto = False
        elif c == '"':
            em_texto = True
        elif c == "{":
            profundidade += 1
        elif c == "}":
            profundidade -= 1
            if profundidade == 0:
                return texto[inicio : posicao + 1]
    return texto[inicio:]


def extrair_json(texto: str) -> str:
    """Tira cercas de código e texto solto em volta do objeto JSON.

    Levanta ``SaidaInvalida`` se não houver nenhum objeto.
    """
    limpo = _BLOCO_DE_RACIOCINIO.sub("", texto)
    for bloco in _CERCA_DE_CODIGO.findall(limpo):
        if "{" in bloco:
            limpo = bloco
            break
    objeto = _primeiro_objeto(limpo)
    if objeto is None:
        raise SaidaInvalida(texto, "A resposta não tem nenhum objeto JSON.")
    return objeto.strip()


def _tirar_virgula_final(saida: list[str]) -> None:
    while saida and saida[-1].isspace():
        saida.pop()
    if saida and saida[-1] == ",":
        saida.pop()


def reparar_json(texto: str) -> str:
    """Conserto local do JSON quebrado mais comum de modelos pequenos (sem chamar modelo)."""
    saida: list[str] = []
    abertos: list[str] = []
    fecha_com: str | None = None  # caractere que fecha o texto em andamento
    i, n = 0, len(texto)
    while i < n:
        c = texto[i]
        if fecha_com is not None:
            if c == "\\" and i + 1 < n:
                saida.append(texto[i : i + 2])
                i += 2
                continue
            if c == fecha_com:
                saida.append('"')
                fecha_com = None
            elif c == '"':
                saida.append('\\"')  # aspas dupla dentro de um texto aberto com aspas simples
            elif c == "\n":
                saida.append("\\n")
            else:
                saida.append(c)
        elif c in _ASPAS_E_FECHAMENTO:
            fecha_com = _ASPAS_E_FECHAMENTO[c]
            saida.append('"')
        elif c in "{[":
            abertos.append("}" if c == "{" else "]")
            saida.append(c)
        elif c in "}]":
            _tirar_virgula_final(saida)
            if abertos:
                abertos.pop()
            saida.append(c)
        elif c.isalpha() or c == "_":
            palavra = re.match(r"[A-Za-z_][A-Za-z_0-9]*", texto[i:])
            trecho = palavra.group(0) if palavra else c
            saida.append(_LITERAIS_DE_PYTHON.get(trecho, trecho))
            i += len(trecho)
            continue
        else:
            saida.append(c)
        i += 1
    if fecha_com is not None:
        saida.append('"')
    _tirar_virgula_final(saida)
    saida.extend(reversed(abertos))
    return "".join(saida)


def _carregar_dict(texto: str) -> tuple[dict[str, Any], bool]:
    """Devolve o objeto e se precisou do conserto local."""
    bruto = extrair_json(texto)
    try:
        dados = json.loads(bruto)
        consertou = False
    except json.JSONDecodeError:
        try:
            dados = json.loads(reparar_json(bruto))
        except json.JSONDecodeError as erro:
            raise SaidaInvalida(texto, f"JSON inválido: {erro.msg} (posição {erro.pos}).") from erro
        consertou = True
    if not isinstance(dados, dict):
        raise SaidaInvalida(texto, "A resposta não é um objeto JSON.")
    return dados, consertou


def _normalizar(dados: dict[str, Any]) -> dict[str, Any]:
    """Arrumações sem risco para o jeito que os modelos costumam errar (sem inventar dados)."""
    dados = dict(dados)
    for campo in ("modo", "risco", "superficie"):
        if isinstance(dados.get(campo), str):
            dados[campo] = dados[campo].strip().lower()
    if isinstance(dados.get("dificuldade"), str) and dados["dificuldade"].strip().isdigit():
        dados["dificuldade"] = int(dados["dificuldade"].strip())
    if isinstance(dados.get("confianca"), str):
        try:
            dados["confianca"] = float(dados["confianca"].replace(",", "."))
        except ValueError:
            pass
    for campo in ("especialistas", "capacidades"):
        if dados.get(campo) is None:
            dados[campo] = []
        elif isinstance(dados[campo], list):
            limpos: list[Any] = []
            for valor in dados[campo]:
                valor = valor.strip().lower() if isinstance(valor, str) else valor
                if valor not in limpos:  # tira repetidos, mantém a ordem
                    limpos.append(valor)
            dados[campo] = limpos
    if dados.get("superficie") is None:
        dados.pop("superficie", None)  # sem superfície = nenhuma; risco nulo NÃO vira "nenhum"
    # A resposta direta só vale com modo = direto e dificuldade = 1 (senão é null, prompt 03).
    if dados.get("modo") != "direto" or dados.get("dificuldade") != 1:
        dados["resposta_direta"] = None
    return dados


def _resumo_dos_erros(erro: ValidationError) -> str:
    """Campos e motivos dos erros, sem repetir os valores recebidos."""
    return "; ".join(
        f"{'.'.join(str(parte) for parte in e['loc']) or 'resposta'}: {e['msg']}"
        for e in erro.errors(include_url=False, include_input=False)
    )


def validar_saida_com_conserto(texto: str) -> tuple[SaidaSistema1, bool]:
    """Valida o texto do modelo; devolve a saída e se foi preciso o conserto local.

    Levanta ``SaidaInvalida`` com os erros (campos e motivos, sem os valores).
    """
    dados, consertou = _carregar_dict(texto)
    try:
        return SaidaSistema1.model_validate(_normalizar(dados)), consertou
    except ValidationError as erro:
        raise SaidaInvalida(texto, _resumo_dos_erros(erro)) from erro


def validar_saida(texto: str) -> SaidaSistema1:
    """Valida o texto do modelo. Levanta ``SaidaInvalida`` com os erros do Pydantic."""
    return validar_saida_com_conserto(texto)[0]
