"""Provedores do usuário: tipos, configuração por chamada e teste da chave.

Especificação: §5 "Como o usuário conecta uma API" e §1 (tabela ``provedores``).

Quem chama este módulo (a rota ``POST /v1/provedores``, o worker) decifra a chave na hora e
entrega um ``ConfigProvedor``. A chave fica em ``SecretStr`` para nunca vazar em log, evento ou
``repr``. Este módulo não conhece o banco nem a cifra.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr

from app.modelos.enumeracoes import TipoProvedor

# Prefixo do nome do modelo no LiteLLM para cada tipo (§5, catálogo). A API compatível com a da
# OpenAI usa ``openai/<modelo>`` junto com ``api_base``.
PREFIXO_LITELLM: dict[TipoProvedor, str] = {
    TipoProvedor.GROQ: "groq",
    TipoProvedor.OPENAI: "openai",
    TipoProvedor.ANTHROPIC: "anthropic",
    TipoProvedor.GOOGLE: "gemini",
    TipoProvedor.OPENROUTER: "openrouter",
    TipoProvedor.COMPATIVEL_OPENAI: "openai",
    TipoProvedor.OLLAMA: "ollama",
}


class ErroProvedor(Exception):
    """Falha ao falar com um provedor. Nunca carrega a chave na mensagem."""


class ChaveInvalida(ErroProvedor):
    """O provedor recusou a chave (teste de conexão ou chamada)."""


class ConfigProvedor(BaseModel):
    """Tudo que o LiteLLM precisa para falar com o provedor do usuário numa chamada."""

    model_config = ConfigDict(frozen=True)

    provedor_id: UUID | None = None
    tipo: TipoProvedor
    api_key: SecretStr | None = None  # None no Ollama local sem chave
    base_url: str | None = None  # obrigatória para compativel_openai e ollama


def parametros_litellm(config: ConfigProvedor) -> dict[str, Any]:
    """Devolve ``api_key`` e ``api_base`` no formato que o LiteLLM/ChatLiteLLM espera."""
    raise NotImplementedError


async def listar_modelos(config: ConfigProvedor) -> list[str]:
    """Testa a chave listando os modelos do provedor (nomes no formato do LiteLLM).

    Levanta ``ChaveInvalida`` se o provedor recusar; a rota devolve 422 e não salva nada.
    """
    raise NotImplementedError
