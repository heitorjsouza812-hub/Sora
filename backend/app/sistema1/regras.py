"""Regras instantâneas do Sistema 1 (antes de qualquer modelo).

Especificação: §7 "Como ligar no Sistema 1" passo 1 ("Regras: saudações, comandos fixos e
verbos de ação externa (enviar, pagar, publicar, apagar). Instantâneo.") e regra de segurança:
as regras só podem acrescentar risco, nunca tirar.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.sistema1.esquemas import Risco

# Verbos que marcam ação externa/destrutiva (lista inicial da §7; a equipe amplia com os dados).
VERBOS_ACAO_EXTERNA: tuple[str, ...] = ("enviar", "pagar", "publicar")
VERBOS_DESTRUTIVOS: tuple[str, ...] = ("apagar",)


class ResultadoRegras(BaseModel):
    """O que as regras conseguiram decidir sozinhas. Campo ``None`` = deixa para o N1."""

    risco: Risco = Risco.NENHUM
    saudacao: bool = False
    comando_fixo: str | None = None  # ex.: "/skill", se houver comandos fixos
    verbos_encontrados: list[str] = Field(default_factory=list)


def aplicar_regras(pedido: str) -> ResultadoRegras:
    """Roda as regras sobre o texto do pedido (sem rede, sem modelo)."""
    raise NotImplementedError


def juntar_risco(*riscos: Risco) -> Risco:
    """O maior risco vence (regras, Laya ou N1): ninguém tira risco, só acrescenta."""
    raise NotImplementedError
