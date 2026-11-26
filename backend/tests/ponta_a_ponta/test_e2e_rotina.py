"""O cron e o webhook usam a mesma execução persistida nas reentregas."""

import asyncio
import base64
import hmac
import time
from datetime import UTC, datetime

import pytest

from tests.ponta_a_ponta.http import sql

pytestmark = [pytest.mark.integracao, pytest.mark.asyncio]


async def _criar(cliente, titulo, segundos):
    resposta = await cliente.post(
        "/v1/rotinas",
        json={"titulo": titulo, "pedido": "Faça o resumo.", "daqui_segundos": segundos},
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


async def _execucoes(cliente, rotina):
    resposta = await cliente.get(f"/v1/rotinas/{rotina}/execucoes")
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


async def _fim(cliente, rotina):
    async with asyncio.timeout(30):
        while True:
            execucoes = await _execucoes(cliente, rotina)
            if execucoes and all(execucao["concluida_em"] for execucao in execucoes):
                assert len(execucoes) == 1
                assert execucoes[0]["status"] == "enviada"
                return execucoes[0]
            await asyncio.sleep(0.2)


async def test_dois_despachos_no_mesmo_minuto_geram_um_disparo(cliente_e2e, mundo):
    # Reserva tempo para dois ticks reais do cron (a cada dez segundos) no mesmo minuto.
    segundo = datetime.now(UTC).second
    if segundo >= 35:
        await asyncio.sleep(60 - segundo)
    rotina = await _criar(cliente_e2e, "Agendamento", 1)
    await mundo.iniciar_worker()
    primeiro = await _fim(cliente_e2e, rotina)

    # A sentinela só fica vencida depois da primeira execução e comprova o próximo despacho.
    sentinela = await _criar(cliente_e2e, "Sentinela do próximo tick", 1)
    segundo_disparo = await _fim(cliente_e2e, sentinela)
    instantes = [
        datetime.fromisoformat(disparo["iniciada_em"]) for disparo in (primeiro, segundo_disparo)
    ]
    assert instantes[0] < instantes[1]
    assert instantes[0].replace(second=0, microsecond=0) == instantes[1].replace(
        second=0, microsecond=0
    )
    assert [e["id"] for e in await _execucoes(cliente_e2e, rotina)] == [primeiro["id"]]
    linhas = await sql(
        mundo,
        "select count(*) as total from rotina_execucoes where rotina_id = :rotina",
        rotina=rotina,
    )
    assert linhas[0].total == 1


async def test_webhook_repetido_gera_uma_execucao(cliente_e2e, mundo):
    rotina = await _criar(cliente_e2e, "Gancho", 86400)
    resposta = await cliente_e2e.post(f"/v1/rotinas/{rotina}/gancho", json={})
    assert resposta.status_code == 201, resposta.text
    gancho = resposta.json()
    corpo = b'{"type":"pedido.pago"}'
    timestamp = str(int(time.time()))
    identificador = "pedido-42"
    chave = base64.b64decode(gancho["segredo"].removeprefix("whsec_"))
    assinatura = hmac.digest(chave, f"{identificador}.{timestamp}.".encode() + corpo, "sha256")
    cabecalhos = {
        "content-type": "application/json",
        "webhook-id": identificador,
        "webhook-timestamp": timestamp,
        "webhook-signature": "v1," + base64.b64encode(assinatura).decode(),
    }
    aceita = await cliente_e2e.post(gancho["url"], content=corpo, headers=cabecalhos)
    repetida = await cliente_e2e.post(gancho["url"], content=corpo, headers=cabecalhos)
    assert (aceita.status_code, aceita.json()["status"]) == (202, "aceita")
    assert (repetida.status_code, repetida.json()["status"]) == (200, "repetida")

    await mundo.iniciar_worker()
    execucao = await _fim(cliente_e2e, rotina)
    assert execucao["origem"] == "webhook"
    assert execucao["id"] == aceita.json()["execucao_id"]
