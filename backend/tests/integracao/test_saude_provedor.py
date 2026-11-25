# ruff: noqa: F811
"""Saúde dos provedores ligada (2026-11-21) com Postgres de verdade: três chamadas que travam ou
recebem 5xx pausam o provedor por 5 minutos (o seletor o deixa de fora); uma resposta boa zera."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import litellm
import pytest
from sqlalchemy import select

from app.agentes.middleware.custo import marcar_custo
from app.llm.saude import provedor_falhou, provedor_respondeu
from app.modelos.enumeracoes import TipoProvedor
from app.modelos.tabelas import Provedor, Usuario
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


class _Modelo:
    metadata: dict | None = None


async def test_tres_falhas_seguidas_pausam_e_resposta_boa_zera(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        await entrar(cliente, mundo.fabrica, "saude@exemplo.com")
    async with mundo.fabrica() as sessao:
        usuario_id = await sessao.scalar(
            select(Usuario.id).where(Usuario.email == "saude@exemplo.com")
        )
        provedor = Provedor(usuario_id=usuario_id, tipo=TipoProvedor.GOOGLE)
        sessao.add(provedor)
        await sessao.commit()
        provedor_id = provedor.id
    modelo = _Modelo()
    marcar_custo(
        modelo,
        modelo="gemini/gemini-3.8-flash",
        provedor_id=provedor_id,
        nivel="N1",
        papel="individual",
        preco_entrada=None,
        preco_saida=None,
    )

    async def estado() -> Provedor:
        async with mundo.fabrica() as sessao:
            linha = await sessao.get(Provedor, provedor_id)
            assert linha is not None
            return linha

    # limite de taxa (429) não conta: quem cuida dele é a espera do limite
    limite = litellm.RateLimitError(message="429", model="m", llm_provider="g")
    await provedor_falhou(modelo, limite)
    assert (await estado()).falhas_seguidas == 0

    prazo = litellm.Timeout(message="prazo", model="m", llm_provider="gemini")
    sobrecarga = litellm.ServiceUnavailableError(message="503", model="m", llm_provider="gemini")
    await provedor_falhou(modelo, prazo)
    await provedor_falhou(modelo, sobrecarga)
    linha = await estado()
    assert linha.falhas_seguidas == 2 and linha.pausado_ate is None
    await provedor_falhou(modelo, prazo)
    linha = await estado()
    assert linha.falhas_seguidas == 3 and linha.pausado_ate is not None
    agora = datetime.now(UTC)
    assert agora + timedelta(minutes=4) < linha.pausado_ate
    assert linha.pausado_ate <= agora + timedelta(minutes=5, seconds=5)

    await provedor_respondeu(modelo)
    linha = await estado()
    assert linha.falhas_seguidas == 0 and linha.pausado_ate is None
