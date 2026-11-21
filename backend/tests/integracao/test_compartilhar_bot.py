# ruff: noqa: F811
"""Compartilhar bot por link, exportar e importar (Onda 3, item 16) com Postgres, Redis e a API
real em uvicorn."""

from __future__ import annotations

import io
import zipfile
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.modelos.tabelas import Agente, Habilidade, Rotina, Usuario
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


async def _criar_bot(cliente: httpx.AsyncClient, auth: dict, nome: str) -> str:
    resposta = await cliente.post(
        "/v1/agentes",
        headers=auth,
        json={
            "nome": nome,
            "funcao": "Escreve posts da cafeteria",
            "papel": "Redator",
            "cor": "#46E8A8",
            "movimento": "ondas",
            "ferramentas": ["buscar_web", "ler_pagina", "computador_agir"],
        },
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


async def test_compartilhar_importar_exportar_e_desligar(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        dono = await entrar(cliente, mundo.fabrica, "dono-bot@exemplo.com")
        bot_id = await _criar_bot(cliente, dono, "Nina")
        async with mundo.fabrica() as sessao:
            agente = await sessao.get(Agente, UUID(bot_id))
            assert agente is not None
            agente.instrucoes = "Use tom leve e sem emojis."
            await sessao.commit()
        for corpo in (
            {"titulo": "Post do dia", "pedido": "Escreva o post.", "cron": "0 9 * * *"},
            {"titulo": "Só hoje", "pedido": "Lembrete.", "daqui_minutos": 30},
        ):
            criada = await cliente.post(
                "/v1/rotinas", headers=dono, json={**corpo, "agente_id": bot_id}
            )
            assert criada.status_code == 201, criada.text
        habilidade = await cliente.post(
            "/v1/habilidades",
            headers=dono,
            json={"nome": "Legenda", "descricao": "Como escrever legenda", "corpo": "1. Curta."},
        )
        assert habilidade.status_code == 201, habilidade.text
        outra = await cliente.post(
            "/v1/habilidades",
            headers=dono,
            json={"nome": "Segredo", "descricao": "Não vai junto", "corpo": "nada"},
        )
        assert outra.status_code == 201

        rota = f"/v1/bots/{bot_id}/compartilhamento"
        assert (await cliente.get(rota, headers=dono)).json() is None
        criado = await cliente.post(
            rota, headers=dono, json={"habilidades": [habilidade.json()["id"]], "com_rotinas": True}
        )
        assert criado.status_code == 201, criado.text
        link = criado.json()
        codigo = link["codigo"]
        assert link["url"].endswith(f"/b/{codigo}")
        bot = link["bot"]
        assert bot["nome"] == "Nina" and bot["instrucoes"] == "Use tom leve e sem emojis."
        assert "computador_agir" not in bot["ferramentas"]  # computador não viaja com o bot
        assert [r["titulo"] for r in bot["rotinas"]] == ["Post do dia"]  # a de uma vez fica
        assert [h["nome"] for h in bot["habilidades"]] == ["Legenda"]
        assert bot["habilidades"][0]["corpo"].strip() == "1. Curta."

        # sem login: a página do link, a prévia e a imagem
        publico = await cliente.get(f"/v1/publico/bots/{codigo}")
        assert publico.status_code == 200 and publico.json()["bot"]["nome"] == "Nina"
        assert "dono-bot" not in publico.text  # nada da conta do dono
        imagem = await cliente.get(f"/v1/publico/bots/{codigo}/imagem.png")
        assert imagem.status_code == 200 and imagem.content.startswith(b"\x89PNG")
        pagina = await cliente.get(f"/b/{codigo}")
        assert pagina.status_code == 200
        assert 'property="og:title" content="Nina · bot feito na Sora"' in pagina.text
        assert f"/v1/publico/bots/{codigo}/imagem.png" in pagina.text
        assert f"url=/compartilhado/{codigo}" in pagina.text
        assert (await cliente.get("/v1/publico/bots/nao-existe-1234")).status_code == 404

        # outra conta: não mexe no bot dos outros, mas pode usar o link
        visita = await entrar(cliente, mundo.fabrica, "visita-bot@exemplo.com")
        assert (await cliente.post(rota, headers=visita, json={})).status_code == 404
        await cliente.post(
            "/v1/habilidades",
            headers=visita,
            json={"nome": "Legenda", "descricao": "Já tinha", "corpo": "minha"},
        )
        usado = await cliente.post(
            "/v1/bots/importar-link", headers=visita, json={"codigo": codigo}
        )
        assert usado.status_code == 201, usado.text
        copia = usado.json()
        assert copia["nome"] == "Nina" and copia["rotinas"] == 1 and copia["habilidades"] == 1
        assert any("pausadas" in a for a in copia["avisos"])
        async with mundo.fabrica() as sessao:
            visita_id = await sessao.scalar(
                select(Usuario.id).where(Usuario.email == "visita-bot@exemplo.com")
            )
            novo = await sessao.get(Agente, UUID(copia["agente_id"]))
            assert novo is not None and novo.usuario_id == visita_id
            assert novo.instrucoes == "Use tom leve e sem emojis."
            assert "computador_agir" not in novo.ferramentas
            [rotina] = (
                await sessao.scalars(select(Rotina).where(Rotina.agente_id == novo.id))
            ).all()
            assert rotina.ativa is False and rotina.proxima_execucao is None
            nomes = set(
                (
                    await sessao.scalars(
                        select(Habilidade.nome).where(Habilidade.usuario_id == visita_id)
                    )
                ).all()
            )
            assert nomes == {"Legenda", "Legenda (importada)"}
        assert (await cliente.get(rota, headers=dono)).json()["usos"] == 1

        # exportar e importar o .zip: o nome repetido ganha número
        exportado = await cliente.post(
            f"/v1/bots/{bot_id}/exportar", headers=dono, json={"com_rotinas": False}
        )
        assert exportado.status_code == 200
        assert exportado.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(exportado.content)) as arquivo:
            assert set(arquivo.namelist()) == {"bot.json", "LEIA-ME.txt"}
        importado = await cliente.post(
            "/v1/bots/importar",
            headers=visita,
            files={"arquivo": ("nina.sora-bot.zip", exportado.content, "application/zip")},
        )
        assert importado.status_code == 201, importado.text
        assert importado.json()["nome"] == "Nina 2" and importado.json()["rotinas"] == 0
        lixo = await cliente.post(
            "/v1/bots/importar",
            headers=visita,
            files={"arquivo": ("x.zip", b"isto nao e zip", "application/zip")},
        )
        assert lixo.status_code == 422
        sem_bot = io.BytesIO()
        with zipfile.ZipFile(sem_bot, "w") as arquivo:
            arquivo.writestr("bot.json", '{"formato": "outro", "bot": {}}')
        errado = await cliente.post(
            "/v1/bots/importar",
            headers=visita,
            files={"arquivo": ("x.zip", sem_bot.getvalue(), "application/zip")},
        )
        assert errado.status_code == 422

        # novo link troca o código; desligar apaga o link na hora
        trocado = (await cliente.post(rota, headers=dono, json={"com_rotinas": False})).json()
        assert trocado["codigo"] != codigo
        assert (await cliente.get(f"/v1/publico/bots/{codigo}")).status_code == 404
        assert (await cliente.delete(rota, headers=dono)).status_code == 204
        assert (await cliente.get(f"/v1/publico/bots/{trocado['codigo']}")).status_code == 404
        assert (await cliente.get(rota, headers=dono)).json() is None
