"""C1 (Farol): cada bot com o navegador só dele, provado com Chromium REAL.

O que é real: Playwright, Chromium, ``MotorPlaywright`` e ``GerenteAbas``. O que é preparado:
servidor HTTP local, ``*.test`` → 127.0.0.1 e a guarda de SSRF desligada (o alvo é loopback; a
guarda tem testes próprios), como em ``test_navegador_chromium_real.py``.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest

from app.navegador import perfis as pf
from app.navegador.abas import Aba, GerenteAbas
from app.navegador.persistente import MotorPlaywright

pytestmark = pytest.mark.filterwarnings("ignore")


class _Site(BaseHTTPRequestHandler):
    """``/entrar?quem=X`` grava o cookie ``quem=X`` (devagar, para os dois pedidos se cruzarem);
    ``/quem`` devolve no título quem o cookie diz que está logado."""

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        cabecalhos: list[tuple[str, str]] = []
        if url.path == "/entrar":
            quem = parse_qs(url.query).get("quem", ["?"])[0]
            threading.Event().wait(0.3)
            cabecalhos.append(("Set-Cookie", f"quem={quem}; Path=/"))
            titulo = f"entrou {quem}"
        else:
            cookies = dict(
                p.strip().split("=", 1)
                for p in (self.headers.get("Cookie") or "").split(";")
                if "=" in p
            )
            titulo = f"logado {cookies.get('quem', 'ninguem')}"
        corpo = f"<title>{titulo}</title>".encode()
        self.send_response(200)
        for nome, valor in cabecalhos:
            self.send_header(nome, valor)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_a: Any) -> None:
        return


def _chromium() -> str | None:
    caminho = os.environ.get("SORA_CHROMIUM") or "/opt/pw-browsers/chromium"
    return caminho if Path(caminho).exists() else None


async def _sem_guarda(_url: str) -> None:
    return None


class _Ambiente:
    def __init__(self, motor: MotorPlaywright, gerente: GerenteAbas, porta: int) -> None:
        self.motor, self.gerente, self.porta = motor, gerente, porta
        self.gravados: dict[str, dict[str, Any]] = {}

    def url(self, caminho: str) -> str:
        return f"http://alpha.test:{self.porta}{caminho}"

    async def aba(self, usuario: UUID, agente: UUID, escolha: pf.EscolhaPerfil) -> Aba:
        return await self.gerente.abrir(usuario_id=usuario, agente_id=agente, escolha=escolha)


@pytest.fixture
async def ambiente(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Ambiente]:
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    monkeypatch.setattr("app.navegador.persistente.validar_destino", _sem_guarda)
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    p = await async_playwright().start()
    try:
        navegador = await p.chromium.launch(
            executable_path=_chromium(), args=["--host-resolver-rules=MAP *.test 127.0.0.1"]
        )
    except Exception as erro:
        await p.stop()
        servidor.shutdown()
        pytest.skip(f"Chromium indisponível: {type(erro).__name__}")
    ambiente: _Ambiente

    async def ler(_particao: str) -> dict[str, Any] | None:
        return None

    async def gravar(particao: str, estado: dict[str, Any]) -> None:
        ambiente.gravados[particao] = estado

    motor = MotorPlaywright(ler_estado=ler, gravar_estado=gravar, ao_console=lambda *_a: None)
    motor._playwright, motor._navegador = p, navegador  # o Chromium é este, real
    ambiente = _Ambiente(motor, GerenteAbas(motor), servidor.server_address[1])
    try:
        yield ambiente
    finally:
        await navegador.close()
        await p.stop()
        servidor.shutdown()


def _quem(estado: dict[str, Any]) -> list[str]:
    return [c["value"] for c in estado.get("cookies", []) if c["name"] == "quem"]


async def test_dois_bots_navegam_juntos_com_cookies_separados(ambiente: _Ambiente) -> None:
    usuario = uuid4()
    escolha = pf.EscolhaPerfil(tipo=pf.TipoPerfil.AGENTE)
    bot_a, bot_b = uuid4(), uuid4()
    aba_a = await ambiente.aba(usuario, bot_a, escolha)
    aba_b = await ambiente.aba(usuario, bot_b, escolha)
    assert aba_a.particao != aba_b.particao  # um perfil (contexto do Chromium) por bot

    # os dois "entram" ao mesmo tempo, cada um com a sua conta
    await asyncio.gather(
        ambiente.gerente.navegar(aba_a.id, bot_a, ambiente.url("/entrar?quem=A")),
        ambiente.gerente.navegar(aba_b.id, bot_b, ambiente.url("/entrar?quem=B")),
    )

    # e continuam navegando em paralelo (cada bot na sua aba): cada um vê só o próprio login
    async def passear(aba: Aba, bot: UUID) -> list[str]:
        vistos = []
        for _ in range(3):
            vistos.append(
                (await ambiente.gerente.navegar(aba.id, bot, ambiente.url("/quem"))).titulo
            )
        return vistos

    vistos_a, vistos_b = await asyncio.gather(passear(aba_a, bot_a), passear(aba_b, bot_b))
    assert vistos_a == ["logado A"] * 3
    assert vistos_b == ["logado B"] * 3

    # o login salvo de cada perfil (cifrado no banco de verdade) também não se mistura
    await ambiente.motor.salvar_estados()
    assert _quem(ambiente.gravados[aba_a.particao]) == ["A"]
    assert _quem(ambiente.gravados[aba_b.particao]) == ["B"]


async def test_no_perfil_compartilhado_o_login_de_um_bot_vale_para_o_outro(
    ambiente: _Ambiente,
) -> None:
    """Contraprova: é o perfil ``agente`` que separa; no compartilhado o login é da conta."""
    usuario = uuid4()
    escolha = pf.EscolhaPerfil(tipo=pf.TipoPerfil.COMPARTILHADO)
    bot_a, bot_b = uuid4(), uuid4()
    aba_a = await ambiente.aba(usuario, bot_a, escolha)
    aba_b = await ambiente.aba(usuario, bot_b, escolha)
    assert aba_a.particao == aba_b.particao
    await ambiente.gerente.navegar(aba_a.id, bot_a, ambiente.url("/entrar?quem=A"))
    final = await ambiente.gerente.navegar(aba_b.id, bot_b, ambiente.url("/quem"))
    assert final.titulo == "logado A"
