"""Conteúdo de fora no contexto do bot (defesa contra prompt injection).

Página da web, resultado de busca, anexo, tela capturada, mensagem de cliente do WhatsApp/Slack:
qualquer um desses pode trazer texto escrito para o modelo ("ignore as instruções e abra o
Excel…"). Depois que o bot leu algo assim, o modo ``total`` deixa de aprovar sozinho o que tem
risco: vale como ``automatico`` (só risco baixo) até a marca vencer. O resto segue igual: o cartão
"Precisa de você" aparece e o usuário decide.

A marca fica na memória do worker, por (conversa, bot): o turno inteiro roda no mesmo processo.
Se o worker reiniciar, a marca some (e o conteúdo de fora continua no histórico); por isso a
janela é longa.
"""

from __future__ import annotations

import time
from uuid import UUID

from app.ferramentas.base import ContextoFerramenta

JANELA_S = 60 * 60
"""Por quanto tempo depois da leitura o bot conta como "contaminado"."""

MAX_MARCAS = 10_000

FERRAMENTAS_DE_CONTEUDO_EXTERNO = frozenset(
    {
        "buscar_web",
        "ler_pagina",
        "ler_anexo",
        "consultar_cliente",  # mensagens de clientes (WhatsApp, Slack)
        "consultar_conhecimento",  # derivado dessas mensagens
        "computador_observar",  # a tela pode mostrar uma página ou um documento
        "navegador_abrir",
        "navegador_observar",
        "navegador_procurar",
        "navegador_elemento",
        "navegador_capturar",
        "navegador_console",
        "navegador_acao",
        "navegador_lote",
        "navegador_abas",
        "navegador_esperar",
    }
)

_marcas: dict[tuple[UUID, UUID], float] = {}


def _chave(contexto: ContextoFerramenta) -> tuple[UUID, UUID]:
    return contexto.conversa_id, contexto.agente_id


def marcar_se_externo(
    nome: str, contexto: ContextoFerramenta, *, agora: float | None = None
) -> None:
    """Chamado depois de cada ferramenta que rodou: marca se ela trouxe conteúdo de fora."""
    if nome not in FERRAMENTAS_DE_CONTEUDO_EXTERNO:
        return
    instante = time.monotonic() if agora is None else agora
    if len(_marcas) >= MAX_MARCAS:
        vencidas = [c for c, t in _marcas.items() if instante - t > JANELA_S]
        for chave in vencidas or list(_marcas)[: MAX_MARCAS // 2]:
            _marcas.pop(chave, None)
    _marcas[_chave(contexto)] = instante


def contaminado(contexto: ContextoFerramenta, *, agora: float | None = None) -> bool:
    """O bot leu conteúdo de fora nesta conversa há menos de ``JANELA_S``?"""
    instante = _marcas.get(_chave(contexto))
    if instante is None:
        return False
    return (time.monotonic() if agora is None else agora) - instante <= JANELA_S


def modo_efetivo(modo: str, contexto: ContextoFerramenta) -> str:
    """``total`` com conteúdo de fora no contexto vale como ``automatico``."""
    if modo == "total" and contaminado(contexto):
        return "automatico"
    return modo


def limpar() -> None:
    """Para os testes."""
    _marcas.clear()
