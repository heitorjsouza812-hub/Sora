"""Teste de capacidades de um modelo fora do catálogo (especificação §5).

"Um modelo fora do catálogo entra como N2 e sem capacidades confirmadas, até ser testado ou
classificado pelo usuário." Este é o teste: duas chamadas curtas ao modelo do próprio usuário,
uma pedindo uma chamada de ferramenta (``ferramentas``) e outra pedindo JSON (``json``). Falha,
prazo estourado ou resposta fora do esperado só deixam a capacidade sem confirmar; nada aqui
levanta erro nem guarda texto do provedor.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from langchain_core.messages import HumanMessage

from app.llm.fabrica import criar_chat_model
from app.llm.provedores import ConfigProvedor

registro = logging.getLogger(__name__)

PRAZO_SONDA_S = 15.0
MAX_SONDAS_POR_CONEXAO = 5
"""Quantos modelos desconhecidos são testados ao conectar; os demais ficam sem confirmar até o
usuário pedir o teste ou classificar."""

Sonda = Callable[[ConfigProvedor, str], Awaitable[list[str]]]

_FERRAMENTA_DE_TESTE = {
    "type": "function",
    "function": {
        "name": "eco",
        "description": "Repete o texto recebido.",
        "parameters": {
            "type": "object",
            "properties": {"texto": {"type": "string"}},
            "required": ["texto"],
        },
    },
}


async def _chamar(config: ConfigProvedor, nome: str, mensagem: str, *, com_ferramenta: bool):
    chat = criar_chat_model(nome, config, max_tokens=64, timeout_s=PRAZO_SONDA_S)
    if com_ferramenta:
        chat = chat.bind_tools([_FERRAMENTA_DE_TESTE])
    return await asyncio.wait_for(chat.ainvoke([HumanMessage(mensagem)]), PRAZO_SONDA_S + 2)


async def sondar_capacidades(config: ConfigProvedor, nome: str) -> list[str]:
    """Capacidades confirmadas pelo teste (``ferramentas`` e/ou ``json``)."""
    confirmadas: list[str] = []
    try:
        resposta = await _chamar(
            config, nome, "Chame a ferramenta eco com o texto oi.", com_ferramenta=True
        )
        if getattr(resposta, "tool_calls", None):
            confirmadas.append("ferramentas")
    except Exception as erro:
        registro.info("teste de ferramentas falhou (%s)", type(erro).__name__)
    try:
        resposta = await _chamar(
            config, nome, 'Responda somente com este JSON: {"ok": true}', com_ferramenta=False
        )
        texto = str(resposta.content)
        inicio, fim = texto.find("{"), texto.rfind("}")
        if inicio >= 0 and fim > inicio and isinstance(json.loads(texto[inicio : fim + 1]), dict):
            confirmadas.append("json")
    except Exception as erro:
        registro.info("teste de JSON falhou (%s)", type(erro).__name__)
    return confirmadas
