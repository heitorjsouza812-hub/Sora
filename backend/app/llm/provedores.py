"""Provedores do usuário: tipos, configuração por chamada e teste da chave.

Especificação: §5 "Como o usuário conecta uma API" e §1 (tabela ``provedores``).

Quem chama este módulo (a rota ``POST /v1/provedores``, o worker) decifra a chave na hora e
entrega um ``ConfigProvedor``. A chave fica em ``SecretStr`` para nunca vazar em log, evento ou
``repr``. Este módulo não conhece o banco nem a cifra, e nenhuma mensagem de erro carrega a chave.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
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

URL_OLLAMA_PADRAO = "http://localhost:11434"
"""Endereço padrão do Ollama quando o usuário não informa ``base_url``."""

# Onde listar os modelos de cada provedor (teste da chave, §5 passo 2).
_URL_LISTAGEM: dict[TipoProvedor, str] = {
    TipoProvedor.GROQ: "https://api.groq.com/openai/v1",
    TipoProvedor.OPENAI: "https://api.openai.com/v1",
    TipoProvedor.OPENROUTER: "https://openrouter.ai/api/v1",
    TipoProvedor.ANTHROPIC: "https://api.anthropic.com/v1",
    TipoProvedor.GOOGLE: "https://generativelanguage.googleapis.com/v1beta",
}

_VERSAO_API_ANTHROPIC = "2023-06-01"
_PRAZO_LISTAGEM_S = 15.0
_CHAVE_SEM_CHAVE = "sem-chave"
"""O LiteLLM exige alguma chave em ``openai/``; servidores compatíveis sem autenticação recebem
este valor fixo."""


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


def _base_sem_barra_final(base_url: str | None) -> str | None:
    if base_url is None:
        return None
    limpa = base_url.strip().rstrip("/")
    return limpa or None


def _chave_em_texto(config: ConfigProvedor) -> str | None:
    if config.api_key is None:
        return None
    chave = config.api_key.get_secret_value().strip()
    return chave or None


def parametros_litellm(config: ConfigProvedor) -> dict[str, Any]:
    """Devolve ``api_key`` e ``api_base`` no formato que o LiteLLM/ChatLiteLLM espera.

    Só entram as chaves que têm valor. Levanta ``ErroProvedor`` se faltar a URL de uma API
    compatível com a da OpenAI.
    """
    base = _base_sem_barra_final(config.base_url)
    chave = _chave_em_texto(config)

    if config.tipo is TipoProvedor.OLLAMA:
        return {"api_base": base or URL_OLLAMA_PADRAO}
    if config.tipo is TipoProvedor.COMPATIVEL_OPENAI:
        if base is None:
            raise ErroProvedor("Informe a URL da API compatível com a da OpenAI.")
        return {"api_base": base, "api_key": chave or _CHAVE_SEM_CHAVE}

    parametros: dict[str, Any] = {}
    if chave is not None:
        parametros["api_key"] = chave
    if base is not None:
        parametros["api_base"] = base
    return parametros


def _requisicao_de_listagem(config: ConfigProvedor) -> tuple[str, dict[str, str]]:
    """URL e cabeçalhos da listagem de modelos do provedor."""
    base = _base_sem_barra_final(config.base_url)
    chave = _chave_em_texto(config) or ""
    tipo = config.tipo

    if tipo is TipoProvedor.OLLAMA:
        return f"{base or URL_OLLAMA_PADRAO}/api/tags", {}
    if tipo is TipoProvedor.ANTHROPIC:
        return (
            f"{base or _URL_LISTAGEM[tipo]}/models?limit=1000",
            {"x-api-key": chave, "anthropic-version": _VERSAO_API_ANTHROPIC},
        )
    if tipo is TipoProvedor.GOOGLE:
        return f"{base or _URL_LISTAGEM[tipo]}/models?pageSize=1000", {"x-goog-api-key": chave}
    if tipo is TipoProvedor.COMPATIVEL_OPENAI:
        if base is None:
            raise ErroProvedor("Informe a URL da API compatível com a da OpenAI.")
        cabecalhos = {"Authorization": f"Bearer {chave}"} if chave else {}
        return f"{base}/models", cabecalhos
    return f"{base or _URL_LISTAGEM[tipo]}/models", {"Authorization": f"Bearer {chave}"}


def _nomes_dos_modelos(config: ConfigProvedor, corpo: Any) -> list[str]:
    """Extrai os ids da resposta e devolve no formato do LiteLLM (``prefixo/id``)."""
    if not isinstance(corpo, dict):
        raise ErroProvedor("O provedor devolveu uma resposta que a Sora não entende.")
    prefixo = PREFIXO_LITELLM[config.tipo]

    if config.tipo is TipoProvedor.OLLAMA:
        itens = [m.get("name") for m in corpo.get("models", []) if isinstance(m, dict)]
    elif config.tipo is TipoProvedor.GOOGLE:
        itens = [
            str(m.get("name", "")).removeprefix("models/")
            for m in corpo.get("models", [])
            if isinstance(m, dict)
        ]
    else:
        itens = [m.get("id") for m in corpo.get("data", []) if isinstance(m, dict)]

    nomes = {f"{prefixo}/{item}" for item in itens if isinstance(item, str) and item}
    return sorted(nomes)


async def listar_modelos(
    config: ConfigProvedor, *, cliente: httpx.AsyncClient | None = None
) -> list[str]:
    """Testa a chave listando os modelos do provedor (nomes no formato do LiteLLM).

    Levanta ``ChaveInvalida`` se o provedor recusar; a rota devolve 422 e não salva nada.
    ``cliente`` existe para os testes injetarem um transporte falso (sem rede).
    """
    url, cabecalhos = _requisicao_de_listagem(config)
    proprio = cliente is None
    http = cliente or httpx.AsyncClient(timeout=_PRAZO_LISTAGEM_S)
    try:
        try:
            resposta = await http.get(url, headers=cabecalhos)
        except httpx.TimeoutException as erro:
            raise ErroProvedor("O provedor demorou demais para responder.") from erro
        except httpx.HTTPError as erro:
            raise ErroProvedor("Não foi possível conectar ao provedor.") from erro
    finally:
        if proprio:
            await http.aclose()

    status = resposta.status_code
    recusas = {400, 401, 403} if config.tipo is TipoProvedor.GOOGLE else {401, 403}
    if status in recusas:
        raise ChaveInvalida("O provedor recusou a chave.")
    if status >= 400:
        raise ErroProvedor(f"O provedor respondeu com erro {status}.")
    try:
        corpo = resposta.json()
    except ValueError as erro:
        raise ErroProvedor("O provedor devolveu uma resposta que a Sora não entende.") from erro
    return _nomes_dos_modelos(config, corpo)
