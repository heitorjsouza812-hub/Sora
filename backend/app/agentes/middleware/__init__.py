"""Middleware dos agentes (especificação §6.1, "Peças de engenharia → middleware").

Um arquivo por peça. As que o LangChain já tem (troca de provedor, limites,
conserto de JSON, resumo) são só configuradas aqui; as nossas herdam de
``AgentMiddleware`` e usam os ganchos antes/depois do modelo e em volta de
cada ferramenta.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.language_models import BaseChatModel

    from app.agentes.montagem import ContextoAgente


def montar_middleware(
    contexto: ContextoAgente, modelos: Sequence[BaseChatModel]
) -> list[AgentMiddleware]:
    """Lista de middleware do papel, na ordem em que deve rodar."""
    from app.agentes.middleware.cancelamento import MiddlewareCancelamento
    from app.agentes.middleware.cerca import MiddlewareCerca
    from app.agentes.middleware.conserto_json import middleware_de_conserto
    from app.agentes.middleware.lembretes import MiddlewareLembretes
    from app.agentes.middleware.limites import middleware_de_limites
    from app.agentes.middleware.loop import MiddlewareLoop
    from app.agentes.middleware.orcamento import MiddlewareOrcamento
    from app.agentes.middleware.passos import MiddlewarePassos
    from app.agentes.middleware.prazo_ferramenta import MiddlewarePrazoFerramenta
    from app.agentes.middleware.saida_grande import MiddlewareSaidaGrande
    from app.agentes.middleware.troca_provedor import montar_middleware_de_troca

    itens: list[AgentMiddleware] = list(
        montar_middleware_de_troca(modelos, ao_trocar=contexto.dependencias.ao_trocar_modelo)
    )
    from app.agentes.middleware.limite_provedor import MiddlewareLimiteDoProvedor

    # Por dentro da nova tentativa e da troca: espera o limite do plano em vez de trocar de modelo.
    itens.append(MiddlewareLimiteDoProvedor(ao_esperar=contexto.dependencias.ao_esperar_limite))
    from app.agentes.middleware.limites import limites_do_agente

    chamadas_modelo, chamadas_ferramenta = limites_do_agente(contexto)
    itens.extend(
        middleware_de_limites(
            max_chamadas_modelo=chamadas_modelo, max_chamadas_ferramenta=chamadas_ferramenta
        )
    )
    itens.extend(
        [middleware_de_conserto(), MiddlewareLoop(), MiddlewarePrazoFerramenta(), MiddlewareCerca()]
    )
    if contexto.papel in {"sora", "individual"}:
        from app.agentes.middleware.encerra_depois_de_falar import (
            MiddlewareEncerraDepoisDeFalar,
        )

        itens.append(MiddlewareLembretes())
        itens.append(MiddlewareEncerraDepoisDeFalar())
    if contexto.cadeia_id is not None and contexto.dependencias.esta_cancelada is not None:
        itens.append(
            MiddlewareCancelamento(
                contexto.cadeia_id, esta_cancelada=contexto.dependencias.esta_cancelada
            )
        )
    deps = contexto.dependencias
    if (
        contexto.cadeia_id is not None
        and deps.orcamento_tokens is not None
        and deps.reservar_tokens is not None
        and deps.corrigir_tokens is not None
    ):
        itens.append(
            MiddlewareOrcamento(
                contexto.cadeia_id,
                deps.orcamento_tokens,
                reservar=deps.reservar_tokens,
                corrigir=deps.corrigir_tokens,
            )
        )
    if (
        contexto.etapa_id is not None
        and deps.iniciar_passo is not None
        and deps.finalizar_passo is not None
    ):
        itens.append(
            MiddlewarePassos(
                contexto.etapa_id,
                contexto.agente_id,
                iniciar=deps.iniciar_passo,
                finalizar=deps.finalizar_passo,
            )
        )
    # Âncora (etapa 4): aprovação por ferramenta e medidor/compactação do contexto.
    from app.agentes.middleware.contexto import MiddlewareContexto
    from app.agentes.middleware.revisor import MiddlewareRevisor
    from app.contexto.porta import PortaContexto
    from app.ferramentas import ambiente
    from app.ferramentas.base import ContextoFerramenta

    itens.append(
        MiddlewareRevisor(
            ContextoFerramenta(
                usuario_id=contexto.usuario_id,
                agente_id=contexto.agente_id,
                conversa_id=contexto.conversa_id,
                cadeia_id=contexto.cadeia_id,
                etapa_id=contexto.etapa_id,
                sem_supervisao=contexto.sem_supervisao,
            )
        )
    )
    if contexto.etapa_id is None and contexto.thread_proprio is None:
        itens.append(
            MiddlewareContexto(
                PortaContexto(
                    redis=ambiente.redis_dos_eventos(),
                    usuario_id=contexto.usuario_id,
                    conversa_id=contexto.conversa_id,
                    agente_id=contexto.agente_id,
                )
            )
        )
    if contexto.etapa_id is not None and deps.ler_mensagens_pendentes is not None:
        from app.agentes.middleware.mensagens import MiddlewareMensagensPendentes

        itens.append(
            MiddlewareMensagensPendentes(contexto.etapa_id, ler=deps.ler_mensagens_pendentes)
        )
    if deps.salvar_saida is not None:
        itens.append(MiddlewareSaidaGrande(contexto.cadeia_id, salvar=deps.salvar_saida))
    return itens
