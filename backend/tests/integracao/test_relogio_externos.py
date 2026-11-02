# ruff: noqa: F811
"""Conectores MCP, Telegram, habilidades e canais do Relógio com banco, API, worker e servidores
locais reais (um servidor MCP de verdade e um Telegram de mentira em HTTP)."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request
from sqlalchemy import select

from app.core.config import obter_configuracao
from app.modelos.tabelas import Conector, Mensagem
from tests.integracao.relogio_base import Mundo, esperar, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import _porta_livre, entrar
from tests.integracao.test_relogio_rotinas import criar, execucoes

pytestmark = pytest.mark.integracao

SERVIDOR = Path(__file__).parent / "auxiliares" / "servidor_mcp.py"


@pytest.fixture
async def servidor_mcp(tmp_path: Path) -> AsyncIterator[tuple[str, Path]]:
    chamadas = tmp_path / "chamadas.txt"
    chamadas.write_text("")
    porta = _porta_livre()
    processo = subprocess.Popen(  # noqa: ASYNC220
        [sys.executable, str(SERVIDOR), str(porta), str(chamadas)]
    )
    try:
        for _ in range(100):
            try:
                async with httpx.AsyncClient() as c:
                    r = await c.get(f"http://127.0.0.1:{porta}/mcp")
                    if r.status_code in (401, 400, 405, 406):
                        break
            except httpx.HTTPError:
                await asyncio.sleep(0.2)
        yield f"http://127.0.0.1:{porta}/mcp", chamadas
    finally:
        processo.terminate()
        processo.wait(10)


async def test_conectores_mcp_de_ponta_a_ponta(
    mundo: Mundo, servidor_mcp: tuple[str, Path]
) -> None:
    url, chamadas = servidor_mcp
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "ext-a@exemplo.com")
        await mundo.iniciar_worker()

        # endereços ruins são recusados
        for ruim in ("http://exemplo.com/mcp", "https://10.0.0.5/mcp", "ftp://x.com/mcp"):
            r = await cliente.post(
                "/v1/conectores", headers=auth, json={"nome": "Ruim", "url": ruim}
            )
            assert r.status_code == 422, (ruim, r.text)

        r = await cliente.post(
            "/v1/conectores",
            headers=auth,
            json={
                "nome": "Clima",
                "url": url,
                "cabecalhos": {"Authorization": "Bearer segredo-do-teste"},
            },
        )
        assert r.status_code == 201, r.text
        conector = r.json()
        assert conector["tem_cabecalhos"] and "segredo" not in r.text
        assert conector["estado"] == "desconhecido"
        async with mundo.fabrica() as sessao:
            linha = await sessao.scalar(select(Conector).where(Conector.nome == "Clima"))
            assert linha is not None and b"segredo-do-teste" not in linha.cabecalhos_cifrados
        dup = await cliente.post("/v1/conectores", headers=auth, json={"nome": "clima", "url": url})
        assert dup.status_code == 422

        teste = (await cliente.post(f"/v1/conectores/{conector['id']}/testar", headers=auth)).json()
        assert teste["ok"], teste
        assert sorted(teste["ferramentas"]) == [
            "mcp__clima__buscar_clima",
            "mcp__clima__enviar_email",
        ]
        lista = (await cliente.get("/v1/conectores", headers=auth)).json()
        assert lista[0]["estado"] == "ok" and lista[0]["n_ferramentas"] == 2

        # rotina sem supervisão: a de leitura funciona; a que escreve nem é oferecida
        leitura = await criar(
            cliente,
            auth,
            titulo="Clima",
            pedido='[chamar:mcp__clima__buscar_clima|{"cidade": "Recife"}]',
        )
        escrita = await criar(
            cliente,
            auth,
            titulo="Email",
            pedido='[chamar:mcp__clima__enviar_email|{"para": "a@b.com", "texto": "oi"}]',
            daqui_segundos=2,
        )

        async def terminou() -> bool:
            for x in (leitura, escrita):
                if not [e for e in await execucoes(cliente, auth, x["id"]) if e["concluida_em"]]:
                    return False
            return True

        await esperar(terminou)
        feita = (await execucoes(cliente, auth, leitura["id"]))[0]
        assert feita["status"] == "enviada" and "Sol em Recife" in feita["resumo"]
        anotado = chamadas.read_text()
        assert "buscar_clima:Recife" in anotado
        assert "enviar_email" not in anotado  # a ferramenta de escrita nunca foi chamada

        # desativar tira as ferramentas; remover apaga
        off = await cliente.patch(
            f"/v1/conectores/{conector['id']}", headers=auth, json={"ativo": False}
        )
        assert off.json()["ativo"] is False
        assert (
            await cliente.delete(f"/v1/conectores/{conector['id']}", headers=auth)
        ).status_code == 204
        assert (await cliente.get("/v1/conectores", headers=auth)).json() == []
        outro = await entrar(cliente, mundo.fabrica, "ext-a2@exemplo.com")
        assert (
            await cliente.post(f"/v1/conectores/{conector['id']}/testar", headers=outro)
        ).status_code == 404


async def test_conector_com_servidor_fora_do_ar_nao_derruba_a_rotina(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "ext-b@exemplo.com")
        await mundo.iniciar_worker()
        morto = f"http://127.0.0.1:{_porta_livre()}/mcp"
        r = await cliente.post("/v1/conectores", headers=auth, json={"nome": "Morto", "url": morto})
        assert r.status_code == 201
        teste = (await cliente.post(f"/v1/conectores/{r.json()['id']}/testar", headers=auth)).json()
        assert teste["ok"] is False and teste["erro"]
        rot = await criar(cliente, auth, titulo="Sem conector")

        async def terminou() -> list[dict]:
            return [e for e in await execucoes(cliente, auth, rot["id"]) if e["concluida_em"]]

        assert (await esperar(terminou))[0]["status"] == "enviada"


async def test_habilidades_crud(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "ext-c@exemplo.com")
        corpo = {
            "nome": "Relatório",
            "descricao": "Para relatórios.",
            "corpo": "1. Junte\n2. Envie",
        }
        r = await cliente.post("/v1/habilidades", headers=auth, json=corpo)
        assert r.status_code == 201, r.text
        hab = r.json()
        assert hab["corpo"].startswith("1. Junte")
        assert (await cliente.post("/v1/habilidades", headers=auth, json=corpo)).status_code == 409
        p = await cliente.patch(
            f"/v1/habilidades/{hab['id']}", headers=auth, json={"corpo": "Novo passo"}
        )
        assert p.json()["corpo"] == "Novo passo" and p.json()["descricao"] == "Para relatórios."
        assert len((await cliente.get("/v1/habilidades", headers=auth)).json()) == 1
        outro = await entrar(cliente, mundo.fabrica, "ext-c2@exemplo.com")
        assert (await cliente.get("/v1/habilidades", headers=outro)).json() == []
        assert (
            await cliente.delete(f"/v1/habilidades/{hab['id']}", headers=outro)
        ).status_code == 404
        assert (
            await cliente.delete(f"/v1/habilidades/{hab['id']}", headers=auth)
        ).status_code == 204


# ---------------------------------------------------------------- Telegram


class TelegramDeMentira:
    def __init__(self) -> None:
        self.enviadas: list[dict[str, Any]] = []
        self.app = FastAPI()

        @self.app.post("/bot{token}/{metodo}")
        async def metodo(token: str, metodo: str, req: Request) -> dict:
            corpo = await req.json()
            if metodo == "sendMessage":
                self.enviadas.append({"token": token, **corpo})
            return {"ok": True, "result": True}


@pytest.fixture
async def telegram() -> AsyncIterator[tuple[TelegramDeMentira, str]]:
    falso = TelegramDeMentira()
    porta = _porta_livre()
    servidor = uvicorn.Server(
        uvicorn.Config(falso.app, host="127.0.0.1", port=porta, log_level="warning")
    )
    tarefa = asyncio.create_task(servidor.serve())
    while not servidor.started:  # noqa: ASYNC110
        await asyncio.sleep(0.05)
    yield falso, f"http://127.0.0.1:{porta}"
    servidor.should_exit = True
    await tarefa


def atualizacao(chat: int, texto: str, mid: int) -> dict:
    return {
        "update_id": mid,
        "message": {
            "message_id": mid,
            "chat": {"id": chat, "type": "private"},
            "from": {"id": chat, "is_bot": False, "first_name": "Ana"},
            "text": texto,
        },
    }


async def test_telegram_vinculo_conversa_e_desvinculo(
    mundo: Mundo, telegram: tuple[TelegramDeMentira, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    falso, url_falsa = telegram
    token = "123456789:AAH-token-do-teste-abcdefghijk"
    segredo = "segredo-do-webhook-1234"
    cab = {"X-Telegram-Bot-Api-Secret-Token": segredo}
    async with httpx.AsyncClient(base_url=mundo.url, timeout=60) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "ext-d@exemplo.com")
        # desligado por padrão
        canais = (await cliente.get("/v1/canais", headers=auth)).json()
        assert canais[0]["disponivel"] is False and canais[0]["vinculos"] == []
        assert (await cliente.post("/v1/canais/telegram/vinculo", headers=auth)).status_code == 404
        assert (
            await cliente.post("/v1/canais/telegram/webhook", json=atualizacao(1, "oi", 1))
        ).status_code == 404

        monkeypatch.setenv("TELEGRAM_TOKEN_BOT", token)
        monkeypatch.setenv("TELEGRAM_SEGREDO_WEBHOOK", segredo)
        monkeypatch.setenv("TELEGRAM_API_URL", url_falsa)
        obter_configuracao.cache_clear()
        await mundo.iniciar_worker()

        assert (await cliente.get("/v1/canais", headers=auth)).json()[0]["disponivel"] is True
        # segredo errado: 401 e nada enviado
        ruim = await cliente.post(
            "/v1/canais/telegram/webhook",
            json=atualizacao(777, "/start X", 1),
            headers={"X-Telegram-Bot-Api-Secret-Token": "errado"},
        )
        assert ruim.status_code == 401 and falso.enviadas == []

        # chat sem vínculo recebe as instruções
        await cliente.post(
            "/v1/canais/telegram/webhook", json=atualizacao(777, "olá", 2), headers=cab
        )
        assert "Configurações" in falso.enviadas[-1]["text"]

        # vínculo
        codigo = (await cliente.post("/v1/canais/telegram/vinculo", headers=auth)).json()["codigo"]
        await cliente.post(
            "/v1/canais/telegram/webhook",
            json=atualizacao(777, f"/start {codigo}", 3),
            headers=cab,
        )
        assert "Pronto" in falso.enviadas[-1]["text"]
        usado = await cliente.post(
            "/v1/canais/telegram/webhook",
            json=atualizacao(888, f"/start {codigo}", 4),
            headers=cab,
        )
        assert usado.status_code == 200 and "não vale mais" in falso.enviadas[-1]["text"]
        vinculos = (await cliente.get("/v1/canais", headers=auth)).json()[0]["vinculos"]
        assert [v["chat_id"] for v in vinculos] == ["777"]

        # conversa: o worker real responde e a resposta volta pelo canal
        antes = len(falso.enviadas)
        await cliente.post(
            "/v1/canais/telegram/webhook",
            json=atualizacao(777, "Qual é a capital?", 5),
            headers=cab,
        )

        async def respondeu() -> bool:
            return len(falso.enviadas) > antes

        await esperar(respondeu, 40)
        resposta = falso.enviadas[-1]
        assert resposta["chat_id"] == "777" and resposta["token"] == token
        assert "modelo falso" in resposta["text"] or "exemplo" in resposta["text"].lower()
        async with mundo.fabrica() as sessao:
            textos = list((await sessao.scalars(select(Mensagem.conteudo))).all())
        assert "Qual é a capital?" in textos  # a mesma conversa aparece no app

        # a mesma mensagem repetida pelo Telegram não responde duas vezes
        total = len(falso.enviadas)
        await cliente.post(
            "/v1/canais/telegram/webhook",
            json=atualizacao(777, "Qual é a capital?", 5),
            headers=cab,
        )
        await asyncio.sleep(4)
        assert len(falso.enviadas) == total

        # desvincular
        assert (
            await cliente.delete(f"/v1/canais/telegram/vinculos/{vinculos[0]['id']}", headers=auth)
        ).status_code == 204
        await cliente.post(
            "/v1/canais/telegram/webhook", json=atualizacao(777, "ainda aí?", 6), headers=cab
        )
        assert "Configurações" in falso.enviadas[-1]["text"]
        assert (
            await cliente.delete(f"/v1/canais/telegram/vinculos/{vinculos[0]['id']}", headers=auth)
        ).status_code == 404


# ---------------------------------------------------------------- voz


async def test_voz_com_a_chave_do_usuario(mundo: Mundo) -> None:
    from sqlalchemy import select as sel

    from app.core.seguranca import cifrar_segredo
    from app.modelos.enumeracoes import TipoProvedor
    from app.modelos.tabelas import Provedor, Usuario

    recebido: dict[str, Any] = {}
    app = FastAPI()

    @app.post("/v1/audio/speech")
    async def fala(req: Request):
        from fastapi.responses import Response

        recebido["auth"] = req.headers["authorization"]
        recebido["corpo"] = await req.json()
        return Response(b"ID3-audio-de-mentira", media_type="audio/mpeg")

    @app.post("/v1/audio/transcriptions")
    async def transcricao(req: Request) -> dict:
        recebido["auth_t"] = req.headers["authorization"]
        recebido["bytes"] = len(await req.body())
        return {"text": "texto transcrito"}

    porta = _porta_livre()
    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="warning")
    )
    tarefa = asyncio.create_task(servidor.serve())
    while not servidor.started:  # noqa: ASYNC110
        await asyncio.sleep(0.05)
    try:
        async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
            auth = await entrar(cliente, mundo.fabrica, "ext-e@exemplo.com")
            sem = await cliente.post("/v1/voz/falar", headers=auth, json={"texto": "oi"})
            assert sem.status_code == 404
            async with mundo.fabrica() as sessao:
                usuario = await sessao.scalar(
                    sel(Usuario).where(Usuario.email == "ext-e@exemplo.com")
                )
                prov = Provedor(
                    usuario_id=usuario.id,
                    tipo=TipoProvedor.COMPATIVEL_OPENAI,
                    base_url=f"http://127.0.0.1:{porta}/v1",
                )
                sessao.add(prov)
                await sessao.flush()
                prov.chave_cifrada = cifrar_segredo(
                    "sk-chave-do-usuario", usuario_id=usuario.id, provedor=str(prov.id)
                )
                await sessao.commit()
            r = await cliente.post(
                "/v1/voz/falar", headers=auth, json={"texto": "**Olá**, tudo bem?"}
            )
            assert r.status_code == 200 and r.content == b"ID3-audio-de-mentira"
            assert r.headers["content-type"].startswith("audio/mpeg")
            assert recebido["auth"] == "Bearer sk-chave-do-usuario"
            assert "**" not in recebido["corpo"]["input"]
            t = await cliente.post(
                "/v1/voz/transcrever",
                headers=auth,
                files={"audio": ("fala.webm", b"\x1aE\xdf\xa3audio", "audio/webm")},
            )
            assert t.status_code == 200 and t.json() == {"texto": "texto transcrito"}
            assert recebido["auth_t"] == "Bearer sk-chave-do-usuario"
            assert "sk-chave" not in t.text
    finally:
        servidor.should_exit = True
        await tarefa
