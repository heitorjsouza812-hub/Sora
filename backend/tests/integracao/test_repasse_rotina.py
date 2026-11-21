# ruff: noqa: F811
"""Rotina que passa o resultado para outro bot (Onda 3, item 13), com Postgres e Redis reais, API
em uvicorn e worker ARQ real (``SORA_MODELO_FALSO=1``).

A rotina é criada por HTTP com o bot seguinte, o cron dispara, o primeiro bot responde e o job
``repassar_resultado_da_rotina`` roda o segundo bot, que fala na conversa dele.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import Agente, Mensagem, Rotina, Usuario
from tests.integracao.relogio_base import Mundo, esperar, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


async def _ids(mundo: Mundo, email: str) -> tuple[UUID, UUID, UUID]:
    """(usuário, Sora, bot novo "Redator")."""
    async with mundo.fabrica() as sessao:
        usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
        sora = await sessao.scalar(
            select(Agente.id).where(Agente.usuario_id == usuario_id, Agente.tipo == TipoAgente.SORA)
        )
        redator = uuid4()
        sessao.add(
            Agente(
                id=redator,
                usuario_id=usuario_id,
                nome="Redator",
                papel="Textos",
                cor="#46E8A8",
                tipo=TipoAgente.INDIVIDUAL,
            )
        )
        await sessao.commit()
    assert usuario_id is not None and sora is not None
    return usuario_id, sora, redator


async def test_resultado_da_rotina_segue_para_o_bot_seguinte(mundo: Mundo) -> None:
    email = "repasse@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        _usuario, sora, redator = await _ids(mundo, email)
        base = {"titulo": "Notícias", "pedido": "Junte as notícias.", "daqui_segundos": 1}

        # o resultado não volta para quem fez a rotina, o bot precisa existir e ter um pedido
        mesmo = await cliente.post(
            "/v1/rotinas",
            headers=auth,
            json={**base, "seguinte_agente_id": str(sora), "seguinte_pedido": "x"},
        )
        assert mesmo.status_code == 422, mesmo.text
        outro = await cliente.post(
            "/v1/rotinas",
            headers=auth,
            json={**base, "seguinte_agente_id": str(uuid4()), "seguinte_pedido": "x"},
        )
        assert outro.status_code == 404, outro.text
        sem_pedido = await cliente.post(
            "/v1/rotinas", headers=auth, json={**base, "seguinte_agente_id": str(redator)}
        )
        assert sem_pedido.status_code == 422, sem_pedido.text
        assert (await cliente.get("/v1/rotinas", headers=auth)).json() == []  # nada ficou

        await mundo.iniciar_worker()
        criada = await cliente.post(
            "/v1/rotinas",
            headers=auth,
            json={
                **base,
                "seguinte_agente_id": str(redator),
                "seguinte_pedido": "Escreva um post curto com isso.",
            },
        )
        assert criada.status_code == 201, criada.text
        rotina = criada.json()
        assert rotina["seguinte_agente_id"] == str(redator)
        assert rotina["seguinte_pedido"] == "Escreva um post curto com isso."

        async def repassada() -> dict | None:
            lista = (
                await cliente.get(f"/v1/rotinas/{rotina['id']}/execucoes", headers=auth)
            ).json()
            return next((e for e in lista if e.get("repasse_status") == "enviada"), None)

        execucao = await esperar(repassada, 90)
        assert execucao["status"] == "enviada" and execucao["repasse_mensagem_id"]
        async with mundo.fabrica() as sessao:
            linha = await sessao.get(Rotina, UUID(rotina["id"]))
            assert linha is not None and linha.seguinte_conversa_id is not None
            assert linha.seguinte_conversa_id != linha.conversa_id
            mensagem = await sessao.get(Mensagem, UUID(execucao["repasse_mensagem_id"]))
            assert mensagem is not None
            assert mensagem.conversa_id == linha.seguinte_conversa_id
            assert mensagem.agente_id == redator
            assert "com o resultado de Sora" in mensagem.conteudo

        # tirar o repasse: null de propósito
        tirado = await cliente.patch(
            f"/v1/rotinas/{rotina['id']}", headers=auth, json={"seguinte_agente_id": None}
        )
        assert tirado.status_code == 200, tirado.text
        assert tirado.json()["seguinte_agente_id"] is None
        assert tirado.json()["seguinte_pedido"] is None
        # mudar só o título não mexe no repasse
        de_novo = await cliente.patch(
            f"/v1/rotinas/{rotina['id']}",
            headers=auth,
            json={"seguinte_agente_id": str(redator), "seguinte_pedido": "Resuma."},
        )
        assert de_novo.json()["seguinte_pedido"] == "Resuma."
        titulo = await cliente.patch(
            f"/v1/rotinas/{rotina['id']}", headers=auth, json={"titulo": "Notícias da manhã"}
        )
        assert titulo.json()["seguinte_agente_id"] == str(redator)

        # bot apagado: o repasse falha com aviso claro ("Rodar agora" em vez de esperar o cron)
        async with mundo.fabrica() as sessao:
            bot = await sessao.get(Agente, redator)
            assert bot is not None

            bot.apagado_em = datetime.now(UTC)
            await sessao.commit()
        executada = await cliente.post(f"/v1/rotinas/{rotina['id']}/executar", headers=auth)
        assert executada.status_code == 202

        async def falhou() -> dict | None:
            lista = (
                await cliente.get(f"/v1/rotinas/{rotina['id']}/execucoes", headers=auth)
            ).json()
            return next((e for e in lista if e.get("repasse_status") == "falhou"), None)

        sem_bot = await esperar(falhou, 90)
        assert "não existe mais" in sem_bot["repasse_erro"]
