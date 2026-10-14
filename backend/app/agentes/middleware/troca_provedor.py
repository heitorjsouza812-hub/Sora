"""Troca de provedor em 429, 5xx ou prazo (especificação §6.1 e §5, "Falhas").

A fábrica única (``ModelRetryMiddleware`` + ``ModelFallbackMiddleware`` com os
modelos na ordem do seletor) mora em ``app/llm/troca.py`` (Bússola). Este
arquivo só a reexporta, para a montagem dos agentes achar todas as peças em
``agentes/middleware/``. Sem lógica própria.
"""

from app.llm.troca import deve_trocar, montar_middleware_de_troca

__all__ = ["deve_trocar", "montar_middleware_de_troca"]
