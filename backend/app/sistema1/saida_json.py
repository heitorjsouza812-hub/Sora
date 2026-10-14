"""Saída JSON do Sistema 1: validar, consertar uma vez, escalar para o N2.

Especificação: prompts 03 ("Se o JSON vier inválido, o backend tenta consertar uma vez e, se
falhar, manda o pedido para o N2"), §6.1 (``ToolErrorMiddleware`` / ``handle_errors`` na saída
estruturada) e §5 (meta: JSON válido de primeira em 99%).
"""

from __future__ import annotations

from app.sistema1.esquemas import SaidaSistema1


class SaidaInvalida(Exception):
    """O JSON não passou na validação nem depois do conserto."""

    def __init__(self, texto_bruto: str, erros: str) -> None:
        super().__init__(erros)
        self.texto_bruto = texto_bruto
        self.erros = erros


def extrair_json(texto: str) -> str:
    """Tira cercas de código e texto solto em volta do objeto JSON."""
    raise NotImplementedError


def validar_saida(texto: str) -> SaidaSistema1:
    """Valida o texto do modelo. Levanta ``SaidaInvalida`` com os erros do Pydantic."""
    raise NotImplementedError
