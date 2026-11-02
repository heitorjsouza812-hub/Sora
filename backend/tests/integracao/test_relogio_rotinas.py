# ruff: noqa: F811
"""Rotinas do Relógio (etapa 4) com Postgres e Redis reais, API em uvicorn e worker ARQ real.

``SORA_MODELO_FALSO=1``. Nada de chamar job direto: a rotina é criada por HTTP, o cron do
worker a dispara e o resultado é lido por HTTP e banco.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modelos.tabelas import Mensagem, Rotina, RotinaExecucao
from tests.integracao.relogio_base import Mundo, esperar, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


async def criar(cliente: httpx.AsyncClient, auth: dict, **campos: Any) -> dict:
    corpo = {"titulo": "Teste", "pedido": "Faça o resumo.", "daqui_segundos": 1, **campos}
    resposta = await cliente.post("/v1/rotinas", headers=auth, json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


async def execucoes(cliente: httpx.AsyncClient, auth: dict, rotina_id: str) -> list[dict]:
    resposta = await cliente.get(f"/v1/rotinas/{rotina_id}/execucoes", headers=auth)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


async def texto_das_mensagens(fabrica: async_sessionmaker, rotina_id: str) -> list[str]:
    async with fabrica() as sessao:
        conversa_id = await sessao.scalar(
            select(Rotina.conversa_id).where(Rotina.id == UUID(rotina_id))
        )
        if conversa_id is None:
            return []
        return list(
            (
                await sessao.scalars(
                    select(Mensagem.conteudo)
                    .where(Mensagem.conversa_id == conversa_id)
                    .order_by(Mensagem.criada_em)
                )
            ).all()
        )


async def test_rotina_roda_sem_supervisao_e_fala_na_conversa(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "rot-a@exemplo.com")
        await mundo.iniciar_worker()
        r = await criar(cliente, auth, titulo="Resumo diário")
        assert r["ativa"] and r["tipo"] == "unico"

        async def terminou() -> list[dict]:
            return [e for e in await execucoes(cliente, auth, r["id"]) if e["concluida_em"]]

        feito = (await esperar(terminou))[0]
        assert feito["status"] == "enviada"
        assert "tudo certo" in feito["resumo"]
        assert feito["mensagem_id"]
        mensagens = await texto_das_mensagens(mundo.fabrica, r["id"])
        assert any("**Resumo diário**" in m and "tudo certo" in m for m in mensagens)
        lista = (await cliente.get("/v1/rotinas", headers=auth)).json()
        achada = next(x for x in lista if x["id"] == r["id"])
        assert achada["ultimo_status"] == "enviada"
        assert achada["ativa"] is False  # única: terminou
        assert achada["proxima_execucao"] is None
        # roda uma vez só, mesmo com vários ticks
        await asyncio.sleep(12)
        assert len(await execucoes(cliente, auth, r["id"])) == 1


async def test_silencio_ferramenta_segura_e_ferramenta_proibida(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "rot-b@exemplo.com")
        await mundo.iniciar_worker()
        quieta = await criar(cliente, auth, pedido="Veja se há novidades [sem-novidades]")
        segura = await criar(
            cliente, auth, titulo="Segura", pedido="Liste [usar:listar]", daqui_segundos=2
        )
        proibida = await criar(
            cliente, auth, titulo="Proibida", pedido="Agende [tentar:agendar]", daqui_segundos=3
        )

        async def todas() -> bool:
            for x in (quieta, segura, proibida):
                feitas = [e for e in await execucoes(cliente, auth, x["id"]) if e["concluida_em"]]
                if not feitas:
                    return False
            return True

        await esperar(todas)
        assert (await execucoes(cliente, auth, quieta["id"]))[0]["status"] == "silenciosa"
        assert await texto_das_mensagens(mundo.fabrica, quieta["id"]) == []
        e = (await execucoes(cliente, auth, segura["id"]))[0]
        assert e["status"] == "enviada" and "Agendamentos vistos" in e["resumo"]
        e = (await execucoes(cliente, auth, proibida["id"]))[0]
        assert e["status"] == "enviada"
        # a ferramenta nem existia para o agente: nenhuma rotina nova nasceu
        async with mundo.fabrica() as sessao:
            assert (
                await sessao.scalar(
                    select(func.count()).select_from(Rotina).where(Rotina.titulo == "intruso")
                )
                == 0
            )


async def test_pausar_retomar_apagar_e_executar_agora(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "rot-c@exemplo.com")
        await mundo.iniciar_worker()
        r = await criar(cliente, auth, a_cada=1, unidade="horas", daqui_segundos=None)
        assert r["tipo"] == "intervalo"
        pausada = await cliente.patch(f"/v1/rotinas/{r['id']}", headers=auth, json={"ativa": False})
        assert pausada.json()["ativa"] is False
        agora = await cliente.post(f"/v1/rotinas/{r['id']}/executar", headers=auth)
        assert agora.status_code == 202

        async def terminou() -> list[dict]:
            return [e for e in await execucoes(cliente, auth, r["id"]) if e["concluida_em"]]

        assert (await esperar(terminou))[0]["status"] == "enviada"  # manual roda mesmo pausada
        retomada = await cliente.patch(f"/v1/rotinas/{r['id']}", headers=auth, json={"ativa": True})
        assert retomada.json()["ativa"] and retomada.json()["proxima_execucao"]
        editada = await cliente.patch(
            f"/v1/rotinas/{r['id']}", headers=auth, json={"titulo": "Novo"}
        )
        assert editada.json()["titulo"] == "Novo"
        assert (await cliente.delete(f"/v1/rotinas/{r['id']}", headers=auth)).status_code == 204
        assert (
            await cliente.get(f"/v1/rotinas/{r['id']}/execucoes", headers=auth)
        ).status_code == 404
        # validações
        dois = await cliente.post(
            "/v1/rotinas",
            headers=auth,
            json={"titulo": "x", "pedido": "y", "cron": "0 9 * * *", "daqui_minutos": 3},
        )
        assert dois.status_code == 422
        rapido = await cliente.post(
            "/v1/rotinas",
            headers=auth,
            json={"titulo": "x", "pedido": "y", "cron": "* * * * *"},
        )
        assert rapido.status_code == 422
        # outro usuário não enxerga
        outro = await entrar(cliente, mundo.fabrica, "rot-c2@exemplo.com")
        meu = await criar(cliente, auth, a_cada=1, unidade="dias", daqui_segundos=None)
        assert (
            await cliente.patch(f"/v1/rotinas/{meu['id']}", headers=outro, json={"ativa": False})
        ).status_code == 404


async def test_vencida_com_worker_parado_roda_uma_vez_ao_reiniciar(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "rot-d@exemplo.com")
        r = await criar(cliente, auth, titulo="Perdida", daqui_segundos=1)  # sem worker
        await asyncio.sleep(3)
        assert await execucoes(cliente, auth, r["id"]) == []
        await mundo.iniciar_worker()

        async def terminou() -> list[dict]:
            return [e for e in await execucoes(cliente, auth, r["id"]) if e["concluida_em"]]

        assert len(await esperar(terminou)) == 1
        # reinicia o worker no meio do dia: nada roda de novo
        await mundo.parar_worker()
        await mundo.iniciar_worker()
        await asyncio.sleep(14)
        assert len(await execucoes(cliente, auth, r["id"])) == 1


async def test_dois_workers_nao_duplicam_a_ocorrencia(mundo: Mundo) -> None:
    from app.rotinas import servico

    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "rot-e@exemplo.com")
        r = await criar(cliente, auth, titulo="Disputada", daqui_segundos=1)
    await asyncio.sleep(2)
    # duas "ticks" ao mesmo tempo, em sessões separadas
    a, b = mundo.fabrica(), mundo.fabrica()
    async with a as sa, b as sb:
        pegas_a = await servico.pegar_vencidas(sa)
        pegas_b = await servico.pegar_vencidas(sb)  # a linha está travada: SKIP LOCKED
        ids_a = {i for i, _ in pegas_a}
        ids_b = {i for i, _ in pegas_b}
        assert UUID(r["id"]) in ids_a
        assert UUID(r["id"]) not in ids_b
        await sa.commit()
        await sb.commit()
    async with mundo.fabrica() as sessao:
        total = await sessao.scalar(select(func.count()).select_from(RotinaExecucao))
        assert total is not None
