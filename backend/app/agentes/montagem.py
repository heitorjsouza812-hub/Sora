"""Montagem dos agentes com ``create_agent`` (especificação §6.1).

1. O seletor (``app/seletor``) devolve a lista de modelos do papel.
2. Cada modelo vira um ``ChatLiteLLM`` (``app/llm``) com a chave do usuário.
3. ``create_agent(model, tools, system_prompt, middleware, checkpointer)``
   com as ferramentas de ``FERRAMENTAS_POR_PAPEL`` e o prompt do arquivo.

A Sora não usa os subagentes prontos do LangChain (Deep Agents): a
coordenação é a cadeia do orquestrador.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

    from app.llm.troca import EventoTroca

registro = logging.getLogger(__name__)

PapelAgente = Literal[
    "sora", "pesquisador", "redator", "designer", "verificador", "individual", "canal"
]

FERRAMENTAS_NAVEGADOR = (
    "navegador_abrir",
    "navegador_abas",
    "navegador_fechar_aba",
    "navegador_capturar",
    "navegador_console",
    "navegador_pedir_ajuda",
    "navegador_observar",
    "navegador_procurar",
    "navegador_elemento",
    "navegador_esperar",
    "navegador_acao",
    "navegador_tecla",
    "navegador_lote",
)

FERRAMENTAS_POR_PAPEL: dict[PapelAgente, tuple[str, ...]] = {
    "sora": (
        "falar",
        "perguntar",
        "criar_agente",
        "propor_grupo",
        "disparar_especialista",
        "ver_especialista",
        "mensagem_especialista",
        "parar_especialista",
        "ler_anexo",
    ),
    "pesquisador": ("buscar_web", "ler_pagina", "ler_anexo", *FERRAMENTAS_NAVEGADOR, "entregar"),
    "redator": ("ler_anexo", "escrever_arquivo", "entregar"),
    "designer": ("ler_anexo", "gerar_imagem", "entregar"),
    "verificador": ("buscar_web", "ler_pagina", "ler_anexo", *FERRAMENTAS_NAVEGADOR, "veredito"),
    "individual": (
        "falar",
        "perguntar",
        "ler_anexo",
        "buscar_web",
        "ler_pagina",
        "escrever_arquivo",
        *FERRAMENTAS_NAVEGADOR,
    ),
    "canal": ("canal_historico", "canal_delegar", "canal_transferir", "canal_resultado"),
}


@dataclass(slots=True)
class DependenciasAgente:
    """Portas de infraestrutura que os middlewares usam sem conhecer o worker."""

    esta_cancelada: Callable[[UUID], Awaitable[bool]] | None = None
    ao_trocar_modelo: Callable[[EventoTroca], Awaitable[None]] | None = None
    ao_esperar_limite: Callable[[int], Awaitable[None]] | None = None
    orcamento_tokens: int | None = None
    reservar_tokens: Callable[[UUID, int, int], Awaitable[bool]] | None = None
    corrigir_tokens: Callable[[UUID, int, int], Awaitable[None]] | None = None
    iniciar_passo: Callable[[UUID, UUID, dict[str, Any]], Awaitable[Any]] | None = None
    finalizar_passo: Callable[[Any, Any | None, BaseException | None], Awaitable[None]] | None = (
        None
    )
    anunciar_prompt: Callable[[UUID, UUID, str], Awaitable[None]] | None = None
    """Conversa direta: publica o passo ``prompt`` (o pedido recebido) no painel Trabalho."""
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
    canal_id: UUID | None = None
    tarefa_canal_id: UUID | None = None
    revisao_canal: int | None = None
    ferramentas_extras: list[str] = field(default_factory=list)
    valores_do_prompt: dict[str, Any] = field(default_factory=dict)
    dependencias: DependenciasAgente = field(default_factory=DependenciasAgente)
    sem_supervisao: bool = False
    """Rotina sem ninguém olhando (Relógio): só ferramentas seguras, navegador efêmero."""
    thread_proprio: str | None = None
    """Thread do checkpointer só desta execução (rotina); senão vale a da conversa/etapa."""
    ferramentas_do_bot: list[str] | None = None
    """``agentes.ferramentas`` do bot de conversa 1:1: só elas (e o essencial) vão direto no
    pedido ao modelo; o resto fica no catálogo (``ferramentas_do_turno.py``)."""
    modelo_enxerga: Callable[[Any], bool] | None = None
    """Só para bots com ``computador_*`` (``app/computador/visao.py``): diz se o modelo de uma
    chamada tem visão. Com ele o middleware anexa a última captura da tela à chamada."""


def nomes_das_ferramentas(contexto: ContextoAgente) -> list[str]:
    """Ferramentas do papel seguidas das extras, sem repetição."""
    from app.agentes.ancora import ferramentas_do_papel

    base = FERRAMENTAS_POR_PAPEL[contexto.papel]
    if contexto.papel == "individual" and contexto.ferramentas_do_bot is not None:
        from app.ferramentas.permissoes import ferramentas_do_agente

        base = tuple(ferramentas_do_agente("individual", contexto.ferramentas_do_bot))
    return list(
        dict.fromkeys(
            (
                *base,
                *ferramentas_do_papel(contexto.papel),
                *contexto.ferramentas_extras,
            )
        )
    )


def montar_prompt_de_sistema(contexto: ContextoAgente) -> str:
    """Prompt de sistema do papel (Sora base, especialista comum + trecho do papel,
    Verificador ou agente individual), já preenchido."""
    from app.agentes.instrucoes import montar_instrucoes
    from app.agentes.prompts import carregar_prompt, preencher

    valores = contexto.valores_do_prompt
    if contexto.sem_supervisao and contexto.papel in {"sora", "individual"}:
        # Rotina: não há ``falar`` (nem ninguém para ouvir). O prompt da Sora manda "sempre falar"
        # e o agente ficava chamando uma ferramenta que não existe até estourar o limite.
        prompt = carregar_prompt("rotina_sem_supervisao")
    elif contexto.papel in {"sora", "individual", "canal"}:
        padroes = {
            "idioma": "pt-BR",
            "perfil_do_agente": (
                "Sora"
                if contexto.papel == "sora"
                else "Agente trabalhando em um canal de equipe"
                if contexto.papel == "canal"
                else "Agente individual"
            ),
            "data_hora": "não informada",
            "fuso": "America/Sao_Paulo",
            "memorias_relevantes": "nenhuma",
            "lista_de_agentes": "nenhum",
        }
        prompt = preencher(carregar_prompt("sora_base"), **(padroes | valores))
    elif contexto.papel == "verificador":
        prompt = preencher(carregar_prompt("verificador"), **({"passos": "nenhum"} | valores))
    else:
        trecho = carregar_prompt(f"especialista_{contexto.papel}")
        prompt = preencher(carregar_prompt("especialista_comum"), trecho_do_papel=trecho, **valores)
    from app.agentes.ferramentas_do_turno import nomes_diretos, nomes_escondidos

    todos = nomes_das_ferramentas(contexto)
    nomes = nomes_diretos(todos, contexto)
    instrucoes = montar_instrucoes(nomes)
    if any(nome in FERRAMENTAS_NAVEGADOR for nome in nomes):
        from app.agentes.ferramentas_do_turno import prompt_do_navegador

        instrucoes += "\n\n" + prompt_do_navegador(contexto.papel)
    elif any(nome in FERRAMENTAS_NAVEGADOR for nome in nomes_escondidos(todos, contexto)):
        instrucoes += "\n\nNavegador no catalogo conectores: carregue o esquema antes de usar."
    if "computador_agir" in nomes:
        # Vela-12: o caminho rápido no computador e conferir antes de dizer que fez
        instrucoes += "\n\n" + carregar_prompt("computador_pc")
    return f"{prompt}\n\n{instrucoes}"


PRAZO_CHECAGEM_IMAGEM_S = 3.0


async def _com_ferramenta_de_imagem(contexto: ContextoAgente) -> ContextoAgente:
    """Dá ``gerar_imagem`` à Sora, aos bots e ao bot de grupo quando o usuário conectou um modelo
    com a capacidade ``imagem``. A imagem sai como anexo da próxima mensagem (``saidas_do_turno``).
    Sem modelo de imagem a ferramenta nem aparece, então o bot não promete o que não faz."""
    from app.llm.falso import modelo_falso_ativo

    if (
        contexto.papel not in {"sora", "individual", "canal"}
        or contexto.sem_supervisao
        or "gerar_imagem" in contexto.ferramentas_extras
        or "gerar_imagem" in nomes_das_ferramentas(contexto)
        or modelo_falso_ativo()
    ):
        return contexto

    async def _tem() -> bool:
        from app.core.banco import fabrica_sessoes
        from app.seletor.repositorio import contexto_do_usuario
        from app.seletor.seletor import tem_modelo_de_imagem

        async with fabrica_sessoes()() as sessao:
            return tem_modelo_de_imagem(await contexto_do_usuario(sessao, contexto.usuario_id))

    try:
        tem = await asyncio.wait_for(_tem(), PRAZO_CHECAGEM_IMAGEM_S)
    except Exception:
        registro.warning("não consegui conferir o modelo de imagem do usuário", exc_info=True)
        return contexto
    if not tem:
        return contexto
    return replace(contexto, ferramentas_extras=[*contexto.ferramentas_extras, "gerar_imagem"])


async def _prompt_do_turno(contexto: ContextoAgente) -> str:
    """Prompt do papel + instruções próprias, memórias, pendências, habilidades e colegas."""
    from app.agentes.ancora import blocos_do_turno

    base = montar_prompt_de_sistema(contexto)
    extras = await blocos_do_turno(contexto)
    return f"{base}\n\n{extras}" if extras else base


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

    contexto = await _com_ferramenta_de_imagem(contexto)
    from app.computador.visao import com_visao_do_computador

    contexto = await com_visao_do_computador(contexto)

    from app.agentes.middleware import montar_middleware
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.registro import criar_ferramentas

    nomes = nomes_das_ferramentas(contexto)
    if contexto.sem_supervisao:
        from app.revisor.politica import pode_sem_supervisao

        nomes = [n for n in nomes if pode_sem_supervisao(n)]
    ferramentas = criar_ferramentas(
        nomes,
        ContextoFerramenta(
            usuario_id=contexto.usuario_id,
            agente_id=contexto.agente_id,
            conversa_id=contexto.conversa_id,
            cadeia_id=contexto.cadeia_id,
            etapa_id=contexto.etapa_id,
            canal_id=contexto.canal_id,
            tarefa_canal_id=contexto.tarefa_canal_id,
            revisao_canal=contexto.revisao_canal,
            sem_supervisao=contexto.sem_supervisao,
        ),
    )
    from app.agentes.ancora import (
        catalogo_dos_conectores,
        catalogo_enxuto,
        navegador_preguicoso,
    )
    from app.agentes.ferramentas_do_turno import PAPEIS_ENXUTOS, nomes_diretos
    from app.conectores.carregar import ferramentas_dos_conectores

    conectores = await ferramentas_dos_conectores(
        contexto.usuario_id, sem_supervisao=contexto.sem_supervisao
    )
    if contexto.papel in PAPEIS_ENXUTOS:
        diretas = set(nomes_diretos([f.name for f in ferramentas], contexto))
        escondidas = [f for f in ferramentas if f.name not in diretas]
        ferramentas = [f for f in ferramentas if f.name in diretas]
        ferramentas += catalogo_enxuto(escondidas, conectores, contexto)
    else:
        ferramentas = navegador_preguicoso(ferramentas, contexto)
        ferramentas += catalogo_dos_conectores(conectores, contexto)
    middleware = montar_middleware(contexto, modelos)
    if "computador_agir" in {f.name for f in ferramentas}:
        # Vela-12: não dizer que fez no PC sem conferir; soltar o PC no fim do turno
        from app.agentes.middleware.conferencia_pc import MiddlewareConferenciaPc

        middleware.append(MiddlewareConferenciaPc(contexto.usuario_id, contexto.agente_id))
    return create_agent(
        model=modelos[0],
        tools=ferramentas,
        system_prompt=await _prompt_do_turno(contexto),
        middleware=middleware,
        checkpointer=checkpointer,
        name=f"sora_{contexto.papel}",
    )


async def rodar_etapa(
    agente: CompiledStateGraph,
    contexto: ContextoAgente,
    entrada: dict[str, Any] | None = None,
    resposta: Any | None = None,
    *,
    continuar_se_parou: bool = False,
) -> dict[str, Any]:
    """Roda (ou retoma com ``Command(resume=resposta)``) o agente da etapa com
    ``ainvoke``, até ``entregar``, ``veredito`` ou uma interrupção.

    ``continuar_se_parou`` é para a nova tentativa depois de um erro (429 no grupo): se a thread
    parou no meio (um passo falhou), continua dali com ``ainvoke(None)``. Mandar a entrada de
    novo acrescentaria o pedido outra vez ao histórico, e o modelo refazia o que já tinha feito
    (ferramentas com efeito rodando duas vezes)."""
    from langgraph.types import Command

    if entrada is not None and resposta is not None:
        raise ValueError("Informe entrada ou resposta de retomada, nunca as duas.")
    if entrada is None and resposta is None:
        raise ValueError("A execução inicial exige entrada; a retomada exige resposta.")

    from app.agentes.checkpointer import thread_da_conversa, thread_da_etapa

    thread_id = (
        contexto.thread_proprio
        if contexto.thread_proprio is not None
        else thread_da_etapa(contexto.etapa_id)
        if contexto.etapa_id is not None
        else thread_da_conversa(contexto.conversa_id)
    )
    configuracao = {"configurable": {"thread_id": thread_id}}
    chamada = Command(resume=resposta) if resposta is not None else entrada
    if continuar_se_parou:
        estado = await agente.aget_state(configuracao)
        if estado.next and not getattr(estado, "interrupts", ()):
            chamada = None
    # ``sync``: o checkpoint de cada passo é gravado antes de o job terminar. No modo padrão
    # (assíncrono) uma pausa recém-criada pode ainda não estar gravada quando o usuário responde.
    resultado = await agente.ainvoke(chamada, config=configuracao, durability="sync")
    return dict(resultado)


async def montar_e_rodar_agente(
    *,
    contexto: ContextoAgente,
    modelos: list[BaseChatModel],
    checkpointer: BaseCheckpointSaver,
    entrada: dict[str, Any] | None = None,
    resposta: Any | None = None,
    continuar_se_parou: bool = False,
) -> dict[str, Any]:
    """Fronteira pública usada pelo worker: monta e executa ou retoma um agente."""
    agente = await montar_agente(contexto, modelos, checkpointer)
    return await rodar_etapa(
        agente, contexto, entrada, resposta, continuar_se_parou=continuar_se_parou
    )
