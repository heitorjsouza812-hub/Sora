# ruff: noqa: F811
"""Webhook das rotinas de ponta a ponta: API em uvicorn, worker ARQ real e modelo falso.

Assinatura Standard Webhooks, filtro por tipo de evento, chamada repetida, troca de segredo,
pausa, teste pela própria Sora e a execução marcada com origem ``webhook``.
"""

from __future__ import annotations

import json
import time

import httpx
import pytest

from app.rotinas.ganchos import assinar
from tests.integracao.relogio_base import Mundo, esperar, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar
from tests.integracao.test_relogio_rotinas import criar, execucoes

pytestmark = pytest.mark.integracao


def _assinado(segredo: str, corpo: dict, msg: str) -> tuple[bytes, dict[str, str]]:
    bruto = json.dumps(corpo).encode()
    ts = int(time.time())
    return bruto, {
        "webhook-id": msg,
        "webhook-timestamp": str(ts),
        "webhook-signature": assinar(segredo, msg, ts, bruto),
        "content-type": "application/json",
    }


async def test_webhook_roda_a_rotina_com_os_dados_e_recusa_o_resto(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "gancho-a@exemplo.com")
        await mundo.iniciar_worker()
        r = await criar(cliente, auth, titulo="Pedido pago", daqui_segundos=86_400)
        rota_gancho = f"/v1/rotinas/{r['id']}/gancho"
        assert (await cliente.get(rota_gancho, headers=auth)).status_code == 404
        # rotina pausada continua respondendo ao webhook
        await cliente.patch(f"/v1/rotinas/{r['id']}", headers=auth, json={"ativa": False})

        filtro = {"tipos_evento": ["pedido.pago"]}
        criado = await cliente.post(rota_gancho, headers=auth, json=filtro)
        assert criado.status_code == 201, criado.text
        gancho = criado.json()
        url, segredo = gancho["url"], gancho["segredo"]
        assert "/v1/ganchos/" in url and segredo.startswith("whsec_")
        assert "segredo" not in (await cliente.get(rota_gancho, headers=auth)).json()

        # sem assinatura e com assinatura errada: 401
        assert (await cliente.post(url, content=b"{}")).status_code == 401
        bruto, cab = _assinado(segredo, {"type": "pedido.pago"}, "msg_1")
        cab["webhook-signature"] = "v1,AAAA"
        assert (await cliente.post(url, content=bruto, headers=cab)).status_code == 401

        # tipo fora do filtro: aceita a chamada, mas não roda
        bruto, cab = _assinado(segredo, {"type": "pedido.criado"}, "msg_2")
        ignorada = await cliente.post(url, content=bruto, headers=cab)
        assert (ignorada.status_code, ignorada.json()["status"]) == (202, "ignorada")

        # a certa roda; a mesma de novo não roda outra vez
        corpo = {"type": "pedido.pago", "data": {"pedido": 123, "valor": "R$ 49,90"}}
        bruto, cab = _assinado(segredo, corpo, "msg_3")
        aceita = await cliente.post(url, content=bruto, headers=cab)
        assert (aceita.status_code, aceita.json()["status"]) == (202, "aceita"), aceita.text
        repetida = await cliente.post(url, content=bruto, headers=cab)
        assert (repetida.status_code, repetida.json()["status"]) == (200, "repetida")

        async def terminou() -> list[dict]:
            return [e for e in await execucoes(cliente, auth, r["id"]) if e["concluida_em"]]

        feitas = await esperar(terminou)
        assert len(feitas) == 1
        assert feitas[0]["origem"] == "webhook"
        assert feitas[0]["id"] == aceita.json()["execucao_id"]
        assert feitas[0]["status"] in {"enviada", "silenciosa"}

        entregas = (await cliente.get(f"{rota_gancho}/entregas", headers=auth)).json()
        assert [(e["tipo_evento"], e["status"]) for e in entregas] == [
            ("pedido.pago", "aceita"),
            ("pedido.criado", "ignorada"),
        ]

        # trocar o segredo: o antigo para de valer na hora, a URL continua
        trocado = (await cliente.post(rota_gancho, headers=auth, json={})).json()
        assert trocado["url"] == url and trocado["segredo"] != segredo
        bruto, cab = _assinado(segredo, corpo, "msg_4")
        assert (await cliente.post(url, content=bruto, headers=cab)).status_code == 401

        # pausado: a URL some (404) e o teste avisa; religado, o teste roda pelo mesmo caminho
        await cliente.patch(rota_gancho, headers=auth, json={"ativo": False})
        bruto, cab = _assinado(trocado["segredo"], corpo, "msg_5")
        assert (await cliente.post(url, content=bruto, headers=cab)).status_code == 404
        assert (await cliente.post(f"{rota_gancho}/teste", headers=auth)).status_code == 409
        await cliente.patch(rota_gancho, headers=auth, json={"ativo": True})
        teste = await cliente.post(f"{rota_gancho}/teste", headers=auth)
        assert (teste.status_code, teste.json()["status"]) == (202, "aceita")

        assert (await cliente.delete(rota_gancho, headers=auth)).status_code == 204
        assert (await cliente.post(url, content=bruto, headers=cab)).status_code == 404


async def test_webhook_de_outra_conta_nao_aparece(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth_a = await entrar(cliente, mundo.fabrica, "gancho-b@exemplo.com")
        auth_b = await entrar(cliente, mundo.fabrica, "gancho-c@exemplo.com")
        r = await criar(cliente, auth_a, titulo="Só da A", daqui_segundos=86_400)
        rota_gancho = f"/v1/rotinas/{r['id']}/gancho"
        assert (await cliente.post(rota_gancho, headers=auth_a, json={})).status_code == 201
        for metodo in ("get", "delete"):
            assert (await getattr(cliente, metodo)(rota_gancho, headers=auth_b)).status_code == 404
        assert (await cliente.post(rota_gancho, headers=auth_b, json={})).status_code == 404
