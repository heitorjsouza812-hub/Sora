"""Revisor: cartão fixo do ``criar_agente`` (fase 1) e revisor de ações (fase 3).

Especificação: plano 01 "Segurança e aprovações", §4 (``criar_agente`` sempre pede aprovação por
cartão fixo, sem modelo revisor) e §6.1 (``interrupt`` do LangGraph; na fase 3,
``HumanInTheLoopMiddleware``). Tabelas: ``aprovacoes``, ``regras_permissao``, ``registro_acoes``.
"""
