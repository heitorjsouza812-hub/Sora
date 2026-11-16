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
    itens.append(
        MiddlewareLimiteDoProvedor(
            ao_esperar=contexto.dependencias.ao_esperar_limite,
            tratar_limite=contexto.canal_id is None,
        )
    )
    from app.agentes.middleware.custo import MiddlewareCustoDasChamadas
    from app.llm.custo import gravar_chamada_do_agente

    async def _gravar_custo(custo: object) -> None:
        await gravar_chamada_do_agente(
            contexto.usuario_id,
            custo,  # type: ignore[arg-type]
            cadeia_id=contexto.cadeia_id,
            etapa_id=contexto.etapa_id,
        )

    # Por dentro da troca de modelo: a linha é do modelo que de fato respondeu.
    itens.append(MiddlewareCustoDasChamadas(_gravar_custo))
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
    if contexto.papel in {"sora", "individual"} and not contexto.sem_supervisao:
        from app.agentes.middleware.encerra_depois_de_falar import (
            MiddlewareEncerraDepoisDeFalar,
        )
        from app.agentes.middleware.fala_unica import MiddlewareFalaUnica

        itens.append(MiddlewareLembretes())
        itens.append(MiddlewareEncerraDepoisDeFalar())
        # Por fora do painel e do revisor: a fala repetida não vira passo nem cartão.
        itens.append(MiddlewareFalaUnica())
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
    etapa_painel = contexto.etapa_id
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
    elif (
        contexto.etapa_id is None
        and contexto.papel in {"sora", "individual"}
        and not contexto.sem_supervisao
        and deps.iniciar_passo is not None
        and deps.finalizar_passo is not None
    ):
        # Conversa direta (bot 1:1, Sora, grupo): sem etapa de verdade, o painel Trabalho recebe os
        # mesmos eventos ``passo`` sob um id sintético estável por turno (não vai para o banco).
        from app.agentes.middleware.passos import PASSOS_DA_CONVERSA_IGNORADOS, id_do_turno

        etapa_painel = id_do_turno(contexto)
        itens.append(
            MiddlewarePassos(
                etapa_painel,
                contexto.agente_id,
                iniciar=deps.iniciar_passo,
                finalizar=deps.finalizar_passo,
                anunciar_prompt=deps.anunciar_prompt,
                ignorar=PASSOS_DA_CONVERSA_IGNORADOS,
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
                # Bot de grupo: sem o grupo no cartão, "Permitir" não achava o turno a retomar.
                canal_id=contexto.canal_id,
                tarefa_canal_id=contexto.tarefa_canal_id,
                revisao_canal=contexto.revisao_canal,
                sem_supervisao=contexto.sem_supervisao,
                etapa_painel=etapa_painel,
            )
        )
    )
    if contexto.etapa_id is None and (
        contexto.thread_proprio is None or ":pedido:" in contexto.thread_proprio
    ):
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
    if contexto.modelo_enxerga is not None:
        # Farol-2: o bot com computador vê a última captura (ou é avisado de que o modelo não vê).
        from app.computador.ferramentas import obter_servico
        from app.computador.visao import MiddlewareVisaoTela

        itens.append(
            MiddlewareVisaoTela(
                contexto.agente_id, servico=obter_servico, tem_visao=contexto.modelo_enxerga
            )
        )
    from app.agentes.middleware.conversa import MiddlewareConversa

    if contexto.canal_id is not None:
        from app.agentes.middleware.conversa import MiddlewareStreamingCanal

        itens.insert(0, MiddlewareStreamingCanal(contexto))
    elif contexto.dependencias.iniciar_passo is not None:
        itens.insert(0, MiddlewareConversa(contexto))
    return itens
