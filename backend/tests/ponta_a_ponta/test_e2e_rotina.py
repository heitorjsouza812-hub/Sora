"""O cron e o webhook usam a mesma execução persistida nas reentregas."""

import asyncio
import base64
import hmac
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from tests.ponta_a_ponta.http import sql

pytestmark = [pytest.mark.integracao, pytest.mark.asyncio]
INSTANTE_DESPACHO = datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC)


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


@pytest.fixture
async def despachar_rotinas(mundo, fila_arq, monkeypatch):
    from workers import rotinas
    from workers.configuracao import WorkerSettings

    class RelogioFixo(datetime):
        @classmethod
        def now(cls, tz=None):
            return (
                INSTANTE_DESPACHO.astimezone(tz) if tz else INSTANTE_DESPACHO.replace(tzinfo=None)
            )

    monkeypatch.setattr(rotinas, "datetime", RelogioFixo)
    barreira = asyncio.Barrier(2)

    async def sincronizar_despachos(ctx):
        if ctx["job_id"].startswith("despacho-e2e:"):
            async with asyncio.timeout(15):
                await barreira.wait()

    await mundo.iniciar_worker(
        functions=[*WorkerSettings.functions, rotinas.disparar_rotinas],
        cron_jobs=[
            cron
            for cron in WorkerSettings.cron_jobs
            if cron.coroutine is not rotinas.disparar_rotinas
        ],
        on_job_start=sincronizar_despachos,
        max_jobs=max(2, WorkerSettings.max_jobs),
    )

    async def disparar():
        job = await fila_arq.enqueue_job("disparar_rotinas", _job_id=f"despacho-e2e:{uuid4()}")
        assert job is not None
        return await job.result(timeout=30, poll_delay=0.1)

    return disparar


async def test_dois_despachos_simultaneos_geram_um_disparo(cliente_e2e, mundo, despachar_rotinas):
    rotina = await _criar(cliente_e2e, "Agendamento", 86400)
    await sql(
        mundo,
        "update rotinas set proxima_execucao = :ocorrencia where id = :id",
        ocorrencia=INSTANTE_DESPACHO - timedelta(seconds=1),
        id=rotina,
    )
    resultados = await asyncio.gather(despachar_rotinas(), despachar_rotinas())
    assert sorted(resultados) == [0, 1]
    execucao = await _fim(cliente_e2e, rotina)
    assert execucao["origem"] == "agenda"
    assert datetime.fromisoformat(execucao["iniciada_em"]) == INSTANTE_DESPACHO
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
