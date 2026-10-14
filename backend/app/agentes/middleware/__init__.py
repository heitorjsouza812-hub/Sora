"""Middleware dos agentes (especificação §6.1, "Peças de engenharia → middleware").

Um arquivo por peça. As que o LangChain já tem (troca de provedor, limites,
conserto de JSON, resumo) são só configuradas aqui; as nossas herdam de
``AgentMiddleware`` e usam os ganchos antes/depois do modelo e em volta de
cada ferramenta.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware

    from app.agentes.montagem import ContextoAgente


def montar_middleware(contexto: ContextoAgente) -> list[AgentMiddleware]:
    """Lista de middleware do papel, na ordem em que deve rodar."""
    raise NotImplementedError
