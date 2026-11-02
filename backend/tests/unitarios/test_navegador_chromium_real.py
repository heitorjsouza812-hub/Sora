"""Decisões de segurança do navegador com Chromium REAL (sem Playwright falso).

O que é real: Playwright, Chromium, ``MotorPlaywright`` (contexto, ``context.route``, filtro,
``navegar``) e ``GerenteAbas``. O que é preparado: um servidor HTTP local e a resolução de
``*.test`` para 127.0.0.1 (``--host-resolver-rules``), e a guarda de SSRF desligada, porque o
alvo é loopback; essa guarda tem testes próprios.
"""

from __future__ import annotations

import os
import threading
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.navegador import perfis as pf
from app.navegador.abas import Aba, GerenteAbas, RevisaoNavegacaoNecessaria
from app.navegador.persistente import MotorPlaywright

pytestmark = pytest.mark.filterwarnings("ignore")


class _Servidor(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        porta = self.server.server_address[1]
        if self.path == "/redireciona":
            self.send_response(302)
            self.send_header("Location", f"http://beta.test:{porta}/destino")
            self.end_headers()
            return
        corpo = (
            f"<title>{self.headers.get('Host')}{self.path}</title>"
            f'<a id="ir" href="http://beta.test:{porta}/destino">ir</a>'
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_a: Any) -> None:
        return


def _chromium() -> str | None:
    caminho = os.environ.get("SORA_CHROMIUM") or "/opt/pw-browsers/chromium"
    return caminho if Path(caminho).exists() else None


async def _nada(*_a: Any, **_k: Any) -> Any:
    return None


async def _sem_guarda(_url: str) -> None:
    return None


COOKIE = {"name": "sessao", "value": "segredo", "domain": "alpha.test", "path": "/"}


class _Ambiente:
    def __init__(self, motor: MotorPlaywright, gerente: GerenteAbas, porta: int) -> None:
        self.motor, self.gerente, self.porta = motor, gerente, porta
        self.estados: dict[str, dict[str, Any] | None] = {}

    def url(self, host: str, caminho: str = "/") -> str:
        return f"http://{host}.test:{self.porta}{caminho}"

    async def aba(self, *, logado: bool, aprovados: tuple[str, ...] = ()) -> tuple[Aba, Any]:
        agente = uuid4()
        escolha = pf.EscolhaPerfil()
        usuario = uuid4()
        particao = pf.particao(usuario, agente, escolha)
        estado: dict[str, Any] = {"cookies": [COOKIE] if logado else [], "origins": []}
        for dominio in aprovados:
            estado = pf.com_dominio_aprovado(estado, dominio)
        self.estados[particao] = estado
        aba = await self.gerente.abrir(usuario_id=usuario, agente_id=agente, escolha=escolha)
        assert aba.particao == particao
        return aba, agente


@pytest.fixture
async def ambiente(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Ambiente]:
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    monkeypatch.setattr("app.navegador.persistente.validar_destino", _sem_guarda)
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Servidor)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    jogo = async_playwright()
    p = await jogo.start()
    try:
        navegador = await p.chromium.launch(
            executable_path=_chromium(), args=["--host-resolver-rules=MAP *.test 127.0.0.1"]
        )
    except Exception as erro:
        await p.stop()
        servidor.shutdown()
        pytest.skip(f"Chromium indisponível: {type(erro).__name__}")
    ambiente: _Ambiente

    async def ler(particao: str) -> dict[str, Any] | None:
        return ambiente.estados.get(particao)

    motor = MotorPlaywright(ler_estado=ler, gravar_estado=_nada, ao_console=lambda *_a: None)
    motor._playwright, motor._navegador = p, navegador  # o Chromium é este, real
    ambiente = _Ambiente(motor, GerenteAbas(motor), servidor.server_address[1])
    try:
        yield ambiente
    finally:
        await navegador.close()
        await p.stop()
        servidor.shutdown()


async def _clicar_e_esperar(motor: MotorPlaywright, aba: Aba) -> str:
    pagina = motor.pagina(aba)
    await pagina.click("#ir")
    await pagina.wait_for_timeout(700)
    return pagina.url


async def test_perfil_logado_clique_para_dominio_novo_e_barrado(ambiente: _Ambiente) -> None:
    aba, agente = await ambiente.aba(logado=True, aprovados=("alpha.test",))
    await ambiente.gerente.navegar(aba.id, agente, ambiente.url("alpha"))  # aprovado: passa
    url = await _clicar_e_esperar(ambiente.motor, aba)
    assert "beta.test" not in url  # a navegação por clique foi abortada
    assert ambiente.motor._bloqueios[aba.particao] == "beta.test"


async def test_perfil_logado_redirect_para_dominio_novo_pede_revisao(
    ambiente: _Ambiente,
) -> None:
    aba, agente = await ambiente.aba(logado=True, aprovados=("alpha.test",))
    with pytest.raises(RevisaoNavegacaoNecessaria, match=r"beta\.test"):
        await ambiente.gerente.navegar(aba.id, agente, ambiente.url("alpha", "/redireciona"))


async def test_perfil_logado_dominio_aprovado_passa_no_clique_e_no_redirect(
    ambiente: _Ambiente,
) -> None:
    aba, agente = await ambiente.aba(logado=True, aprovados=("alpha.test", "beta.test"))
    await ambiente.gerente.navegar(aba.id, agente, ambiente.url("alpha"))
    assert "beta.test" in await _clicar_e_esperar(ambiente.motor, aba)
    final = await ambiente.gerente.navegar(aba.id, agente, ambiente.url("alpha", "/redireciona"))
    assert "beta.test" in final.url


async def test_aprovar_depois_libera_o_dominio_na_mesma_aba(ambiente: _Ambiente) -> None:
    aba, agente = await ambiente.aba(logado=True, aprovados=("alpha.test",))
    with pytest.raises(RevisaoNavegacaoNecessaria):
        await ambiente.gerente.navegar(aba.id, agente, ambiente.url("alpha", "/redireciona"))
    usuario = aba.usuario_id
    assert await ambiente.gerente.aprovar_dominio(aba.id, usuario, ambiente.url("beta")) == (
        "beta.test"
    )
    final = await ambiente.gerente.navegar(aba.id, agente, ambiente.url("alpha", "/redireciona"))
    assert "beta.test" in final.url


async def test_perfil_sem_login_passa_no_clique_e_no_redirect(ambiente: _Ambiente) -> None:
    aba, agente = await ambiente.aba(logado=False)
    final = await ambiente.gerente.navegar(aba.id, agente, ambiente.url("alpha", "/redireciona"))
    assert "beta.test" in final.url
    await ambiente.gerente.navegar(aba.id, agente, ambiente.url("alpha"))
    assert "beta.test" in await _clicar_e_esperar(ambiente.motor, aba)


async def test_rotina_efemera_nao_ve_cookie_do_perfil_logado(ambiente: _Ambiente) -> None:
    agente, usuario = uuid4(), uuid4()
    escolha = pf.EscolhaPerfil()
    ambiente.estados[pf.particao(usuario, agente, escolha)] = {"cookies": [COOKIE], "origins": []}
    aba = await ambiente.gerente.abrir(
        usuario_id=usuario, agente_id=agente, escolha=escolha, sem_supervisao=True
    )
    await ambiente.gerente.navegar(aba.id, agente, ambiente.url("alpha"), sem_supervisao=True)
    cookies = await ambiente.motor._contextos[aba.particao].cookies()
    assert cookies == []  # contexto efêmero: nada do perfil salvo
    await ambiente.gerente.fechar(aba.id, agente, sem_supervisao=True)
    assert aba.particao not in ambiente.motor._contextos  # contexto destruído ao fechar
