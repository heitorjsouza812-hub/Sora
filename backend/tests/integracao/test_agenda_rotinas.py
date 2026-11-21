# ruff: noqa: F811
"""Agenda das rotinas e feed .ics com Postgres e Redis reais (API em uvicorn)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar
from tests.integracao.test_relogio_rotinas import criar

pytestmark = pytest.mark.integracao


async def test_agenda_mostra_previstas_e_o_feed_ics_e_secreto(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "agenda-a@exemplo.com")
        outra = await entrar(cliente, mundo.fabrica, "agenda-b@exemplo.com")
        diaria = await criar(
            cliente, auth, titulo="Resumo; diário", cron="0 9 * * *", daqui_segundos=None
        )
        pausada = await criar(
            cliente, auth, titulo="Pausada", cron="0 10 * * *", daqui_segundos=None
        )
        await cliente.patch(f"/v1/rotinas/{pausada['id']}", headers=auth, json={"ativa": False})
        await criar(cliente, outra, titulo="Da outra conta", cron="0 9 * * *", daqui_segundos=None)

        agora = datetime.now(UTC)
        params = {"de": agora.isoformat(), "ate": (agora + timedelta(days=7)).isoformat()}
        agenda = (await cliente.get("/v1/agenda", headers=auth, params=params)).json()
        titulos = {o["titulo"] for o in agenda["previstas"]}
        assert titulos == {"Resumo; diário"}
        assert 6 <= len(agenda["previstas"]) <= 7
        demais = {"de": agora.isoformat(), "ate": (agora + timedelta(days=90)).isoformat()}
        assert (await cliente.get("/v1/agenda", headers=auth, params=demais)).status_code == 422

        assert (await cliente.get("/v1/agenda/feed", headers=auth)).json()["ligado"] is False
        ligado = (await cliente.post("/v1/agenda/feed", headers=auth)).json()
        url = ligado["url"]
        assert url.endswith(".ics") and "/v1/agenda/feed/" in url
        assert (await cliente.get("/v1/agenda/feed", headers=auth)).json() == {
            "ligado": True,
            "criado_em": ligado["criado_em"],
            "url": None,
        }
        feed = await cliente.get(url)  # sem login: o segredo é o endereço
        assert feed.status_code == 200
        assert feed.headers["content-type"].startswith("text/calendar")
        assert r"SUMMARY:Resumo\; diário" in feed.text  # o ";" do título vai escapado
        assert "Da outra conta" not in feed.text and "Pausada" not in feed.text
        assert feed.text.count("BEGIN:VEVENT") >= 28

        # trocar o endereço: o antigo para de funcionar; desligar: some de vez
        novo = (await cliente.post("/v1/agenda/feed", headers=auth)).json()["url"]
        assert (await cliente.get(url)).status_code == 404
        assert (await cliente.get(novo)).status_code == 200
        assert (await cliente.delete("/v1/agenda/feed", headers=auth)).status_code == 204
        assert (await cliente.get(novo)).status_code == 404
        assert (await cliente.get("/v1/agenda/feed/qualquer-coisa.ics")).status_code == 404
        assert diaria["id"]
