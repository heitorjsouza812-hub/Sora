"""Mensagens do assistente no formato que cada provedor aceita (B1 do Prumo-3).

O ``ChatLiteLLM`` devolve ao provedor, em cada mensagem anterior do assistente, o
``reasoning_content`` que o modelo gerou (``langchain_litellm`` ``_convert_message_to_dict``).
Groq, OpenAI e a maioria das APIs compatíveis respondem **400** a esse campo
("property 'reasoning_content' is unsupported"), o que quebrava toda chamada ao modelo depois da
primeira ferramenta. Só quem lê o raciocínio de volta o mantém.

Regra geral: o campo sai das mensagens, a não ser que o tipo do provedor esteja em
``ACEITAM_RACIOCINIO_NO_HISTORICO``.
"""

from __future__ import annotations

from typing import Any

from app.modelos.enumeracoes import TipoProvedor

CAMPOS_DE_RACIOCINIO = ("reasoning_content", "reasoning", "reasoning_details")
"""Campos extras que um modelo de raciocínio põe na mensagem e a API de chat não aceita de volta."""

ACEITAM_RACIOCINIO_NO_HISTORICO: frozenset[TipoProvedor] = frozenset({TipoProvedor.GOOGLE})
"""O Gemini (via LiteLLM) lê o raciocínio das mensagens anteriores; os demais recusam ou ignoram.
Anthropic usa ``thinking_blocks``, que o LiteLLM monta por conta própria."""


def aceita_raciocinio_no_historico(tipo: TipoProvedor | None) -> bool:
    return tipo in ACEITAM_RACIOCINIO_NO_HISTORICO


def sem_campos_de_raciocinio(mensagens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cópia da lista de mensagens (formato OpenAI) sem os campos de raciocínio."""
    limpas: list[dict[str, Any]] = []
    for mensagem in mensagens:
        if any(campo in mensagem for campo in CAMPOS_DE_RACIOCINIO):
            mensagem = {k: v for k, v in mensagem.items() if k not in CAMPOS_DE_RACIOCINIO}
        limpas.append(mensagem)
    return limpas
