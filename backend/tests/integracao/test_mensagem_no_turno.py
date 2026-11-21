# ruff: noqa: F811
""" "Mandar agora" com Postgres e Redis reais: a entrega atômica no turno vivo (script Lua) e a
rota, que cai no caminho normal quando não há resposta rodando."""

from __future__ import annotations

import os
from uuid import UUID

import httpx
import pytest
from redis.asyncio import Redis

from app.ferramentas import ambiente
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


async def test_mandar_agora_entra_no_turno_vivo_ou_segue_normal(mundo: Mundo) -> None:
    redis = Redis.from_url(os.environ["REDIS_URL"])
    try:
        async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
            auth = await entrar(cliente, mundo.fabrica, "agora-a@exemplo.com")
            pedido = {"texto": "Crie o logo."}
            criada = await cliente.post("/v1/conversas", headers=auth, json=pedido)
            assert criada.status_code == 201, criada.text
            conversa = UUID(criada.json()["id"])
            rota = f"/v1/conversas/{conversa}/mensagens/agora"

            # sem resposta rodando: segue pelo caminho normal
            normal = await cliente.post(rota, headers=auth, json={"texto": "e mais uma coisa"})
            assert normal.status_code == 202, normal.text
            assert normal.json()["no_turno"] is False
            assert await ambiente.esvaziar_correio_do_turno(conversa, redis) == []

            # com o turno vivo: vai para o correio do turno, e a mensagem fica no histórico
            await ambiente.marcar_turno_vivo(conversa, "marca-1", redis)
            agora = await cliente.post(rota, headers=auth, json={"texto": "Use a cor azul."})
            assert agora.json()["no_turno"] is True
            [item] = await ambiente.esvaziar_correio_do_turno(conversa, redis)
            assert item == {"mensagem_id": agora.json()["mensagem_id"], "texto": "Use a cor azul."}
            mensagens = (
                await cliente.get(f"/v1/conversas/{conversa}/mensagens", headers=auth)
            ).json()
            textos = [m.get("conteudo") or m.get("texto") for m in mensagens]
            assert "Use a cor azul." in str(textos)

            # só a marca do próprio turno apaga; depois disso, volta a seguir normal
            await ambiente.desmarcar_turno_vivo(conversa, "outra-marca", redis)
            assert await ambiente.entregar_no_turno(conversa, UUID(int=1), "x", redis) is True
            await ambiente.desmarcar_turno_vivo(conversa, "marca-1", redis)
            assert await ambiente.entregar_no_turno(conversa, UUID(int=2), "y", redis) is False

            # outra conta não manda na conversa dos outros
            auth_b = await entrar(cliente, mundo.fabrica, "agora-b@exemplo.com")
            alheia = await cliente.post(rota, headers=auth_b, json={"texto": "oi"})
            assert alheia.status_code == 404
    finally:
        await redis.aclose()
