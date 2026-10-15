"""Fábrica de ``ChatLiteLLM`` (pacote ``langchain-litellm``).

Especificação: §6.1 "Como uma etapa roda", passo 2: cada modelo da lista do seletor vira um
``ChatLiteLLM`` com a chave e a URL do provedor do usuário. Com ``SORA_MODELO_FALSO=1`` a fábrica
devolve o modelo falso de ``falso.py`` (§8.5).

A chave entra só como parâmetro do ``ChatLiteLLM`` (o campo ``api_key`` dele não aparece no
``repr``). Não há nova tentativa interna (``max_retries=0``): quem repete e troca de modelo é o
middleware de ``troca.py``, para a troca aparecer na linha do tempo.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.llm.falso import criar_modelo_falso, modelo_falso_ativo
from app.llm.provedores import (
    ClienteLiteLLMProtegido,
    ConfigProvedor,
    parametros_litellm,
    politica_de_rede,
)

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
    """Cria o ``ChatLiteLLM`` de um modelo do usuário (nome no formato do LiteLLM).

    Não faz chamada de rede: só monta o objeto. Com ``SORA_MODELO_FALSO=1`` devolve o modelo
    falso do papel (a chave nem é lida).
    """
    if modelo_falso_ativo():
        return criar_modelo_falso(papel or "")

    from langchain_litellm import ChatLiteLLM

    politica = politica_de_rede()
    parametros = parametros_litellm(provedor, politica)
    chat = ChatLiteLLM(
        model=modelo,
        temperature=temperatura,
        max_tokens=max_tokens,
        request_timeout=timeout_s,
        streaming=streaming,
        max_retries=0,
        **parametros,
    )
    if "api_base" in parametros and not politica.rede_local:
        # URL escolhida pelo usuário: cada chamada confere o IP antes de sair (API-02).
        chat.client = ClienteLiteLLMProtegido()
    return chat


def criar_modelos_na_ordem(
    candidatos: Sequence[tuple[str, ConfigProvedor]],
    *,
    papel: str | None = None,
    temperatura: float = 0.0,
    streaming: bool = False,
) -> list[BaseChatModel]:
    """Cria um ``ChatLiteLLM`` por candidato, mantendo a ordem do seletor (o 1º é o principal)."""
    return [
        criar_chat_model(
            modelo, provedor, papel=papel, temperatura=temperatura, streaming=streaming
        )
        for modelo, provedor in candidatos
    ]
