"""Modelo falso para desenvolver sem chave e sem custo.

Especificação: §8.5 "Modelo falso para desenvolver". Com ``SORA_MODELO_FALSO=1`` o ``llm/`` troca
todos os modelos por um ``GenericFakeChatModel`` com respostas prontas (triagem, plano, entregas
e veredito de exemplo). O backend inteiro roda no PC emitindo os mesmos eventos do modo real.
Nunca fica ligado em produção.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

VARIAVEL_MODELO_FALSO = "SORA_MODELO_FALSO"

# Papéis (política do seletor, §5) que ganham uma sequência de respostas prontas.
PAPEIS_COM_RESPOSTA_PRONTA: tuple[str, ...] = (
    "sistema1",
    "sora",
    "planejador",
    "pesquisador",
    "redator",
    "designer",
    "verificador",
    "agente_individual",
)


def modelo_falso_ativo() -> bool:
    """True quando ``SORA_MODELO_FALSO=1`` está no ambiente."""
    raise NotImplementedError


def garantir_fora_de_producao(ambiente: str) -> None:
    """Levanta erro na subida se o modelo falso estiver ligado em ``ambiente == "producao"``."""
    raise NotImplementedError


def respostas_prontas(papel: str) -> list[str]:
    """Respostas de exemplo de um papel (JSON válido para sistema1/planejador/verificador)."""
    raise NotImplementedError


def criar_modelo_falso(papel: str) -> BaseChatModel:
    """``GenericFakeChatModel`` com as respostas do papel, com suporte a ``bind_tools``."""
    raise NotImplementedError
