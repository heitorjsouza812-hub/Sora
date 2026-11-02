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
    itens.extend(middleware_de_limites(max_chamadas_modelo=10, max_chamadas_ferramenta=10))
    itens.extend(
        [middleware_de_conserto(), MiddlewareLoop(), MiddlewarePrazoFerramenta(), MiddlewareCerca()]
    )
    if contexto.papel in {"sora", "individual"}:
        itens.append(MiddlewareLembretes())
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
    if deps.salvar_saida is not None:
        itens.append(MiddlewareSaidaGrande(contexto.cadeia_id, salvar=deps.salvar_saida))
    return itens
