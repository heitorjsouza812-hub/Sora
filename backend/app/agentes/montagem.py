"""Montagem dos agentes com ``create_agent`` (especificação §6.1).

1. O seletor (``app/seletor``) devolve a lista de modelos do papel.
2. Cada modelo vira um ``ChatLiteLLM`` (``app/llm``) com a chave do usuário.
3. ``create_agent(model, tools, system_prompt, middleware, checkpointer)``
   com as ferramentas de ``FERRAMENTAS_POR_PAPEL`` e o prompt do arquivo.

A Sora não usa os subagentes prontos do LangChain (Deep Agents): a
coordenação é a cadeia do orquestrador.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

PapelAgente = Literal["sora", "pesquisador", "redator", "designer", "verificador", "individual"]


@dataclass(slots=True)
class ContextoAgente:
    """Tudo que o worker sabe antes de montar o agente."""

    usuario_id: UUID
    agente_id: UUID
    conversa_id: UUID
    papel: PapelAgente
    cadeia_id: UUID | None = None
    etapa_id: UUID | None = None
    ferramentas_extras: list[str] = field(default_factory=list)
    valores_do_prompt: dict[str, Any] = field(default_factory=dict)


def montar_prompt_de_sistema(contexto: ContextoAgente) -> str:
    """Prompt de sistema do papel (Sora base, especialista comum + trecho do papel,
    Verificador ou agente individual), já preenchido."""
    raise NotImplementedError


async def montar_agente(
    contexto: ContextoAgente,
    modelos: list[BaseChatModel],
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    """Monta o agente com ``create_agent``: o primeiro modelo da lista é o
    principal e os outros entram no ``ModelFallbackMiddleware``."""
    raise NotImplementedError


async def rodar_etapa(
    agente: CompiledStateGraph, contexto: ContextoAgente, resposta: Any | None = None
) -> dict[str, Any]:
    """Roda (ou retoma com ``Command(resume=resposta)``) o agente da etapa com
    ``ainvoke``, até ``entregar``, ``veredito`` ou uma interrupção."""
    raise NotImplementedError
