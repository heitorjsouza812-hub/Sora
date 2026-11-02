"""Agentes da Sora em LangChain 1.x (especificação §6.1).

Montagem com ``create_agent`` (Sora, especialistas e agentes individuais),
carregamento dos prompts de ``backend/prompts``, aparência (nome, cor e
movimento escolhidos por código) e o middleware das peças de engenharia.
"""

from app.agentes.montagem import (
    ContextoAgente,
    DependenciasAgente,
    montar_e_rodar_agente,
)

__all__ = ["ContextoAgente", "DependenciasAgente", "montar_e_rodar_agente"]
