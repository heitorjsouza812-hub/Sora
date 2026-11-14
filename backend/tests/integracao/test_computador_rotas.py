# ruff: noqa: F811
"""Rotas do computador e do navegador por bot (Farol, C1/C2) com Postgres, Redis e a API reais.

Bot novo nasce com navegador próprio; o estado e a captura do computador só aparecem para o
dono do bot; desligar só vale para o dono.
"""

from __future__ import annotations

import base64

import httpx
import pytest
from redis.asyncio import Redis

from app.computador.servico import CHAVE_CAPTURA, CHAVE_ESTADO
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao

PNG = b"\x89PNG\r\n\x1a\nfalso"


@pytest.fixture(autouse=True)
def _fila_limpa():
    """A fila da API é global; vinda de outro módulo, estaria presa a um loop já fechado."""
    from workers.fila import configurar_fila

    configurar_fila(None)
    yield
    configurar_fila(None)


async def test_bot_novo_navegador_proprio_e_computador_so_do_dono(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        a = await entrar(cliente, mundo.fabrica, "farol-a@exemplo.com")
        b = await entrar(cliente, mundo.fabrica, "farol-b@exemplo.com")

        criado = await cliente.post(
            "/v1/agentes", json={"descricao": "Pesquisa preços de café"}, headers=a
        )
        assert criado.status_code == 201, criado.text
        bot = criado.json()
        assert bot["perfil_navegador"] == "agente"  # C1: navegador só dele
        lista = (await cliente.get("/v1/agentes", headers=a)).json()
        assert next(x for x in lista if x["id"] == bot["id"])["perfil_navegador"] == "agente"
        sora = (await cliente.get("/v1/agentes/sora", headers=a)).json()
        assert sora["perfil_navegador"] == "compartilhado"  # a Sora usa o login da conta
        detalhe = await cliente.get(f"/v1/agentes/{bot['id']}/navegador", headers=a)
        assert detalhe.json()["tipo"] == "agente"

        # trocar e voltar para o perfil próprio
        troca = await cliente.put(
            f"/v1/agentes/{bot['id']}/navegador", json={"tipo": "compartilhado"}, headers=a
        )
        assert troca.json()["tipo"] == "compartilhado"
        volta = await cliente.put(
            f"/v1/agentes/{bot['id']}/navegador", json={"tipo": "agente"}, headers=a
        )
        assert volta.status_code == 200 and volta.json()["tipo"] == "agente"

        base = f"/v1/agentes/{bot['id']}/computador"
        estado = await cliente.get(base, headers=a)
        assert estado.status_code == 200
        assert estado.json()["ligado"] is False and estado.json()["disponivel"] is False
        assert (await cliente.get(f"{base}/captura", headers=a)).status_code == 404

        # o worker gravou uma tela (simulada aqui direto no Redis)
        redis = Redis.from_url(mundo.url_redis)
        try:
            await redis.set(CHAVE_CAPTURA.format(agente_id=bot["id"]), base64.b64encode(PNG))
            await redis.set(
                CHAVE_ESTADO.format(agente_id=bot["id"]),
                '{"ligado": true, "alvo": "virtual", "largura": 1280, "altura": 800, '
                '"janela_ativa": "Chromium", "acao": "Clicou em 1,1", '
                '"atualizado_em": "2026-11-14T15:00:00+00:00"}',
            )
        finally:
            await redis.aclose()
        estado = (await cliente.get(base, headers=a)).json()
        assert estado["ligado"] is True and estado["largura"] == 1280
        assert estado["janela_ativa"] == "Chromium"
        captura = await cliente.get(f"{base}/captura", headers=a)
        assert captura.status_code == 200 and captura.content == PNG
        assert captura.headers["content-type"] == "image/png"
        assert captura.headers["cache-control"] == "no-store"

        # outra conta não vê nem desliga
        for resposta in (
            await cliente.get(base, headers=b),
            await cliente.get(f"{base}/captura", headers=b),
            await cliente.post(f"{base}/desligar", headers=b),
        ):
            assert resposta.status_code == 404
        assert (await cliente.get(base)).status_code == 401
        assert (await cliente.post(f"{base}/desligar", headers=a)).status_code == 202
