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
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.llm.falso import criar_modelo_falso, modelo_falso_ativo
from app.llm.provedores import (
    ClienteLiteLLMProtegido,
    ConfigProvedor,
    parametros_litellm,
    politica_de_rede,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


@lru_cache(maxsize=1)
def _classe_do_chat() -> type:
    """``ChatLiteLLM`` que tira o raciocínio das mensagens do assistente antes de enviar.

    Sem isso o Groq (e a maioria das APIs) responde 400 a ``reasoning_content`` na segunda
    chamada de qualquer turno com ferramenta (B1 do Prumo-3). O campo ``enviar_raciocinio``
    liga o envio só para os provedores que o leem (``app/llm/mensagens.py``).
    """
    from langchain_litellm import ChatLiteLLM

    from app.llm.mensagens import sem_campos_de_raciocinio

    class ChatLiteLLMSora(ChatLiteLLM):
        enviar_raciocinio: bool = False

        def _create_message_dicts(self, messages: Any, stop: Any) -> Any:
            dicts, params = super()._create_message_dicts(messages, stop)
            if not self.enviar_raciocinio:
                dicts = sem_campos_de_raciocinio(dicts)
            return dicts, params

    return ChatLiteLLMSora


def criar_chat_model(
    modelo: str,
    provedor: ConfigProvedor,
    *,
    papel: str | None = None,
    temperatura: float = 0.0,
    max_tokens: int | None = None,
    timeout_s: float | None = None,
    streaming: bool = False,
    raciocinio: str | None = None,
) -> BaseChatModel:
    """Cria o ``ChatLiteLLM`` de um modelo do usuário (nome no formato do LiteLLM).

    Não faz chamada de rede: só monta o objeto. Com ``SORA_MODELO_FALSO=1`` devolve o modelo
    falso do papel (a chave nem é lida). ``raciocinio`` é um nível de ``app/llm/raciocinio.py``
    que o modelo aceita (nível que ele não aceita, ou ``None``, não muda nada).
    """
    if modelo_falso_ativo():
        return criar_modelo_falso(papel or "")

    from app.llm.mensagens import aceita_raciocinio_no_historico
    from app.llm.raciocinio import parametros_de_raciocinio

    politica = politica_de_rede()
    parametros = parametros_litellm(provedor, politica)
    # O cliente da OpenAI por baixo refaz 429 sozinho (2 vezes, escondido); quem espera o
    # limite e conta as tentativas é o MiddlewareLimiteDoProvedor.
    extras: dict[str, Any] = {"max_retries": 0}
    ajuste = parametros_de_raciocinio(modelo, raciocinio) if raciocinio else None
    if ajuste is not None:
        extras.update(ajuste.extras)
        if ajuste.temperatura is not None:
            temperatura = ajuste.temperatura
        if ajuste.max_tokens_minimo is not None:
            max_tokens = max(max_tokens or 0, ajuste.max_tokens_minimo)
    chat = _classe_do_chat()(
        enviar_raciocinio=aceita_raciocinio_no_historico(provedor.tipo),
        model=modelo,
        temperature=temperatura,
        max_tokens=max_tokens,
        request_timeout=timeout_s,
        streaming=streaming,
        max_retries=0,
        model_kwargs=extras,
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
    raciocinios: Sequence[str | None] | None = None,
) -> list[BaseChatModel]:
    """Cria um ``ChatLiteLLM`` por candidato, mantendo a ordem do seletor (o 1º é o principal).
    ``raciocinios`` traz o nível de cada candidato (mesma ordem); ``None`` = sem ajuste."""
    niveis = list(raciocinios) if raciocinios is not None else [None] * len(candidatos)
    return [
        criar_chat_model(
            modelo,
            provedor,
            papel=papel,
            temperatura=temperatura,
            streaming=streaming,
            raciocinio=nivel,
        )
        for (modelo, provedor), nivel in zip(candidatos, niveis, strict=True)
    ]
