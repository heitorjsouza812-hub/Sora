"""Saúde dos provedores (especificação §5, regra "Falhas"), agora ligada no worker.

Cada chamada de um bot que estoura o prazo ou recebe erro do servidor (5xx, como o "503 high
demand" do Gemini sobrecarregado) soma uma falha no provedor dela; na terceira seguida
(``config/politica.yaml``), o provedor fica pausado por 5 minutos e o seletor passa a escolher
modelos de outros provedores. Uma resposta boa zera a conta. Limite de taxa (429) não conta: quem
cuida dele é a espera do ``MiddlewareLimiteDoProvedor`` e as chaves extras.

Nada aqui derruba a chamada do bot: erro ao gravar a saúde só vai para o log.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import or_, update

from app.llm.troca import EstadoSaude, MotivoTroca, classificar_erro, registrar_falha

registro = logging.getLogger(__name__)

MOTIVOS_QUE_CONTAM = frozenset({MotivoTroca.PRAZO, MotivoTroca.ERRO_DO_SERVIDOR})


def provedor_do_modelo(modelo: Any) -> UUID | None:
    """O provedor que ``marcar_custo`` deixou no modelo (``None`` no modelo falso dos testes)."""
    from app.agentes.middleware.custo import CHAVE_DE_CUSTO

    dados = (getattr(modelo, "metadata", None) or {}).get(CHAVE_DE_CUSTO) or {}
    try:
        return UUID(str(dados["provedor_id"]))
    except (KeyError, TypeError, ValueError):
        return None


class ArmazemSaudeSQL:
    """``ArmazemSaude`` sobre as colunas ``falhas_seguidas`` e ``pausado_ate`` de ``provedores``."""

    async def obter(self, provedor_id: UUID) -> EstadoSaude:
        from app.core.banco import fabrica_sessoes
        from app.modelos.tabelas import Provedor

        async with fabrica_sessoes()() as sessao:
            linha = await sessao.get(Provedor, provedor_id)
            if linha is None:
                return EstadoSaude(provedor_id=provedor_id)
            return EstadoSaude(
                provedor_id=provedor_id,
                falhas_seguidas=linha.falhas_seguidas,
                pausado_ate=linha.pausado_ate,
            )

    async def salvar(self, estado: EstadoSaude) -> None:
        from app.core.banco import fabrica_sessoes
        from app.modelos.tabelas import Provedor

        async with fabrica_sessoes()() as sessao:
            await sessao.execute(
                update(Provedor)
                .where(Provedor.id == estado.provedor_id)
                .values(falhas_seguidas=estado.falhas_seguidas, pausado_ate=estado.pausado_ate)
            )
            await sessao.commit()


async def provedor_falhou(modelo: Any, erro: BaseException) -> None:
    provedor_id = provedor_do_modelo(modelo)
    if provedor_id is None or classificar_erro(erro) not in MOTIVOS_QUE_CONTAM:
        return
    from app.seletor.politica import obter_politica

    try:
        politica = obter_politica()
        estado = await registrar_falha(
            ArmazemSaudeSQL(),
            provedor_id,
            falhas_para_pausar=politica.limites.falhas_para_pausar_provedor,
            pausa_minutos=politica.limites.pausa_provedor_minutos,
        )
        if estado.pausado_ate is not None:
            registro.warning(
                "provedor %s pausado até %s (%s falhas seguidas)",
                provedor_id,
                estado.pausado_ate.isoformat(),
                estado.falhas_seguidas,
            )
    except Exception:
        registro.warning("não consegui registrar a falha do provedor", exc_info=True)


async def provedor_respondeu(modelo: Any) -> None:
    provedor_id = provedor_do_modelo(modelo)
    if provedor_id is None:
        return
    from app.core.banco import fabrica_sessoes
    from app.modelos.tabelas import Provedor

    try:
        async with fabrica_sessoes()() as sessao:
            await sessao.execute(
                update(Provedor)
                .where(
                    Provedor.id == provedor_id,
                    or_(Provedor.falhas_seguidas > 0, Provedor.pausado_ate.is_not(None)),
                )
                .values(falhas_seguidas=0, pausado_ate=None)
            )
            await sessao.commit()
    except Exception:
        registro.warning("não consegui zerar as falhas do provedor", exc_info=True)
