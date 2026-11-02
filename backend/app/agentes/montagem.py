"""Montagem dos agentes com ``create_agent`` (especificação §6.1).

1. O seletor (``app/seletor``) devolve a lista de modelos do papel.
2. Cada modelo vira um ``ChatLiteLLM`` (``app/llm``) com a chave do usuário.
3. ``create_agent(model, tools, system_prompt, middleware, checkpointer)``
   com as ferramentas de ``FERRAMENTAS_POR_PAPEL`` e o prompt do arquivo.

A Sora não usa os subagentes prontos do LangChain (Deep Agents): a
coordenação é a cadeia do orquestrador.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

    from app.llm.troca import EventoTroca

PapelAgente = Literal["sora", "pesquisador", "redator", "designer", "verificador", "individual"]

FERRAMENTAS_POR_PAPEL: dict[PapelAgente, tuple[str, ...]] = {
    "sora": (
        "falar",
        "perguntar",
        "disparar_especialista",
        "ver_especialista",
        "mensagem_especialista",
        "parar_especialista",
        "ler_anexo",
    ),
    "pesquisador": ("buscar_web", "ler_pagina", "ler_anexo", "entregar"),
    "redator": ("ler_anexo", "escrever_arquivo", "entregar"),
    "designer": ("ler_anexo", "gerar_imagem", "entregar"),
    "verificador": ("buscar_web", "ler_pagina", "ler_anexo", "veredito"),
    "individual": (
        "falar",
        "perguntar",
        "ler_anexo",
        "buscar_web",
        "ler_pagina",
        "escrever_arquivo",
    ),
}


@dataclass(slots=True)
class DependenciasAgente:
    """Portas de infraestrutura que os middlewares usam sem conhecer o worker."""

    esta_cancelada: Callable[[UUID], Awaitable[bool]] | None = None
    ao_trocar_modelo: Callable[[EventoTroca], Awaitable[None]] | None = None
    orcamento_tokens: int | None = None
    reservar_tokens: Callable[[UUID, int, int], Awaitable[bool]] | None = None
    corrigir_tokens: Callable[[UUID, int, int], Awaitable[None]] | None = None
    iniciar_passo: Callable[[UUID, UUID, dict[str, Any]], Awaitable[Any]] | None = None
    finalizar_passo: Callable[[Any, Any | None, BaseException | None], Awaitable[None]] | None = (
        None
    )
    salvar_saida: Callable[[UUID | None, str], Awaitable[str]] | None = None
    ler_mensagens_pendentes: Callable[[UUID], Awaitable[list[str]]] | None = None


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
    dependencias: DependenciasAgente = field(default_factory=DependenciasAgente)


def nomes_das_ferramentas(contexto: ContextoAgente) -> list[str]:
    """Ferramentas do papel seguidas das extras, sem repetição."""
    return list(
        dict.fromkeys((*FERRAMENTAS_POR_PAPEL[contexto.papel], *contexto.ferramentas_extras))
    )


def montar_prompt_de_sistema(contexto: ContextoAgente) -> str:
    """Prompt de sistema do papel (Sora base, especialista comum + trecho do papel,
    Verificador ou agente individual), já preenchido."""
    from app.agentes.instrucoes import montar_instrucoes
    from app.agentes.prompts import carregar_prompt, preencher

    valores = contexto.valores_do_prompt
    if contexto.papel in {"sora", "individual"}:
        padroes = {
            "idioma": "pt-BR",
            "perfil_do_agente": "Sora" if contexto.papel == "sora" else "Agente individual",
            "data_hora": "não informada",
            "fuso": "America/Sao_Paulo",
            "memorias_relevantes": "nenhuma",
            "lista_de_agentes": "nenhum",
        }
        prompt = preencher(carregar_prompt("sora_base"), **(padroes | valores))
    elif contexto.papel == "verificador":
        prompt = preencher(carregar_prompt("verificador"), **valores)
    else:
        trecho = carregar_prompt(f"especialista_{contexto.papel}")
        prompt = preencher(carregar_prompt("especialista_comum"), trecho_do_papel=trecho, **valores)
    return f"{prompt}\n\n{montar_instrucoes(nomes_das_ferramentas(contexto))}"


async def montar_agente(
    contexto: ContextoAgente,
    modelos: list[BaseChatModel],
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    """Monta o agente com ``create_agent``: o primeiro modelo da lista é o
    principal e os outros entram no ``ModelFallbackMiddleware``."""
    if not modelos:
        raise ValueError("A lista de modelos do seletor está vazia.")

    from langchain.agents import create_agent

    from app.agentes.middleware import montar_middleware
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.registro import criar_ferramentas

    nomes = nomes_das_ferramentas(contexto)
    ferramentas = criar_ferramentas(
        nomes,
        ContextoFerramenta(
            usuario_id=contexto.usuario_id,
            agente_id=contexto.agente_id,
            conversa_id=contexto.conversa_id,
            cadeia_id=contexto.cadeia_id,
            etapa_id=contexto.etapa_id,
        ),
    )
    return create_agent(
        model=modelos[0],
        tools=ferramentas,
        system_prompt=montar_prompt_de_sistema(contexto),
        middleware=montar_middleware(contexto, modelos),
        checkpointer=checkpointer,
        name=f"sora_{contexto.papel}",
    )


async def rodar_etapa(
    agente: CompiledStateGraph,
    contexto: ContextoAgente,
    entrada: dict[str, Any] | None = None,
    resposta: Any | None = None,
) -> dict[str, Any]:
    """Roda (ou retoma com ``Command(resume=resposta)``) o agente da etapa com
    ``ainvoke``, até ``entregar``, ``veredito`` ou uma interrupção."""
    from langgraph.types import Command

    if entrada is not None and resposta is not None:
        raise ValueError("Informe entrada ou resposta de retomada, nunca as duas.")
    if entrada is None and resposta is None:
        raise ValueError("A execução inicial exige entrada; a retomada exige resposta.")

    from app.agentes.checkpointer import thread_da_conversa, thread_da_etapa

    thread_id = (
        thread_da_etapa(contexto.etapa_id)
        if contexto.etapa_id is not None
        else thread_da_conversa(contexto.conversa_id)
    )
    configuracao = {"configurable": {"thread_id": thread_id}}
    chamada = Command(resume=resposta) if resposta is not None else entrada
    resultado = await agente.ainvoke(chamada, config=configuracao)
    return dict(resultado)


async def montar_e_rodar_agente(
    *,
    contexto: ContextoAgente,
    modelos: list[BaseChatModel],
    checkpointer: BaseCheckpointSaver,
    entrada: dict[str, Any] | None = None,
    resposta: Any | None = None,
) -> dict[str, Any]:
    """Fronteira pública usada pelo worker: monta e executa ou retoma um agente."""
    agente = await montar_agente(contexto, modelos, checkpointer)
    return await rodar_etapa(agente, contexto, entrada, resposta)
