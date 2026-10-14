"""Fábrica de ``ChatLiteLLM`` (pacote ``langchain-litellm``).

Especificação: §6.1 "Como uma etapa roda", passo 2: cada modelo da lista do seletor vira um
``ChatLiteLLM`` com a chave e a URL do provedor do usuário. Com ``SORA_MODELO_FALSO=1`` a fábrica
devolve o modelo falso de ``falso.py`` (§8.5).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.llm.provedores import ConfigProvedor

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


def criar_chat_model(
    modelo: str,
    provedor: ConfigProvedor,
    *,
    papel: str | None = None,
    temperatura: float = 0.0,
    max_tokens: int | None = None,
    timeout_s: float | None = None,
    streaming: bool = False,
) -> BaseChatModel:
    """Cria o ``ChatLiteLLM`` de um modelo do usuário (nome no formato do LiteLLM)."""
    raise NotImplementedError


def criar_modelos_na_ordem(
    candidatos: Sequence[tuple[str, ConfigProvedor]],
    *,
    papel: str | None = None,
    temperatura: float = 0.0,
    streaming: bool = False,
) -> list[BaseChatModel]:
    """Cria um ``ChatLiteLLM`` por candidato, mantendo a ordem do seletor (o 1º é o principal)."""
    raise NotImplementedError
