"""Achados do Faro na Fase A: política contextual, filtro de rota, rotina e infra do navegador."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.navegador import perfis as pf
from app.navegador.abas import Aba, GerenteAbas, RevisaoNavegacaoNecessaria
from app.revisor.politica import (
    dominio_registravel,
    navegacao_exige_revisao,
    politica_contextual_navegador,
)

RAIZ = Path(__file__).resolve().parents[3]


def _carregar(caminho: str, nome: str) -> Any:
    spec = importlib.util.spec_from_file_location(nome, RAIZ / caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# ---------- achado 1 e 2: regra de revisão ----------


def test_filtro_depende_so_de_login_e_dominio_nao_aprovado() -> None:
    url = "https://app.exemplo.com/x"
    assert not navegacao_exige_revisao(url, perfil_tem_login=False, dominios_aprovados=set())
    assert navegacao_exige_revisao(url, perfil_tem_login=True, dominios_aprovados=set())
    assert not navegacao_exige_revisao(
        url, perfil_tem_login=True, dominios_aprovados={"exemplo.com"}
    )


def test_url_sem_esquema_e_vazia_nao_escapam_da_revisao() -> None:
    assert dominio_registravel("evil.com/login") == "evil.com"
    for url in ("evil.com", "evil.com/login", "//evil.com", "  evil.com:8080/x ", "", "   ", "://"):
        assert navegacao_exige_revisao(url, perfil_tem_login=True, dominios_aprovados=set()), url
    politica = politica_contextual_navegador(
        "navegador_abrir", url="evil.com", perfil_tem_login=True, dominios_aprovados=set()
    )
    assert politica.value == "revisor"


def test_sufixos_publicos_e_idn() -> None:
    assert dominio_registravel("https://banco.com.pe/") == "banco.com.pe"  # fora de lista fixa
    assert dominio_registravel("https://x.cliente.github.io/") == "cliente.github.io"
    assert dominio_registravel("https://café.com/") == dominio_registravel("xn--caf-dma.com")
    # aprovado em unicode, URL em punycode
    assert not navegacao_exige_revisao(
        "https://xn--caf-dma.com/", perfil_tem_login=True, dominios_aprovados={"café.com"}
    )
    assert navegacao_exige_revisao(
        "https://outro.com.pe/", perfil_tem_login=True, dominios_aprovados={"banco.com.pe"}
    )


class _Motor:
    def __init__(self) -> None:
        self.estados: dict[str, dict[str, Any]] = {}

    async def abrir_pagina(self, aba: Aba) -> None: ...

    async def navegar(self, aba: Aba, url: str) -> tuple[str, str]:
        return url, "t"

    async def descarregar(self, aba: Aba) -> None: ...

    async def fechar(self, aba: Aba) -> None: ...

    async def capturar(self, aba: Aba) -> bytes:
        return b""

    async def limpar_particao(self, particao_: str) -> None: ...

    async def contexto_politica(self, aba: Aba) -> tuple[bool, set[str]]:
        estado = self.estados.get(aba.particao)
        return pf.perfil_tem_login(estado), pf.dominios_aprovados(estado)

    async def aprovar_dominio(self, aba: Aba, dominio: str) -> None:
        self.estados[aba.particao] = pf.com_dominio_aprovado(
            self.estados.get(aba.particao), dominio
        )


async def test_aprovar_exemplo_com_sem_esquema_funciona() -> None:
    motor = _Motor()
    gerente = GerenteAbas(motor)  # type: ignore[arg-type]
    usuario, agente = uuid4(), uuid4()
    aba = await gerente.abrir(usuario_id=usuario, agente_id=agente, escolha=pf.EscolhaPerfil())
    motor.estados[aba.particao] = {"cookies": [{"name": "s", "value": "v"}], "origins": []}
    with pytest.raises(RevisaoNavegacaoNecessaria):
        await gerente.navegar(aba.id, agente, "exemplo.com")
    assert await gerente.aprovar_dominio(aba.id, usuario, "exemplo.com") == "exemplo.com"
    await gerente.navegar(aba.id, agente, "https://www.exemplo.com/a")


# (filtro de rota, redirecionamento e contexto efêmero: testes com Chromium real em
# test_navegador_chromium_real.py)


# ---------- achado 6: rotina e aba efêmera ----------


async def test_rotina_nao_reusa_aba_persistente() -> None:
    motor = _Motor()
    gerente = GerenteAbas(motor)  # type: ignore[arg-type]
    usuario, agente = uuid4(), uuid4()
    logada = await gerente.abrir(usuario_id=usuario, agente_id=agente, escolha=pf.EscolhaPerfil())
    with pytest.raises(ErroFerramenta, match="Rotinas"):
        await gerente.usar(logada.id, agente, sem_supervisao=True)
    with pytest.raises(ErroFerramenta, match="Rotinas"):
        await gerente.navegar(logada.id, agente, "https://a.com/", sem_supervisao=True)
    efemera = await gerente.abrir(
        usuario_id=usuario, agente_id=agente, escolha=pf.EscolhaPerfil(), sem_supervisao=True
    )
    assert [a.id for a in gerente.do_agente(agente, so_efemeras=True)] == [efemera.id]
    await gerente.usar(efemera.id, agente, sem_supervisao=True)
    assert ContextoFerramenta(uuid4(), agente, uuid4(), sem_supervisao=True).sem_supervisao


# ---------- achado 3: proxy ----------


@pytest.mark.parametrize(
    "ip",
    [
        "::ffff:169.254.169.254",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "::ffff:100.100.100.200",
        "::ffff:192.168.0.1",
        "100.64.0.1",
        "100.100.100.200",
        "::1",
        "fd00::1",
        "2002:a00:1::1",  # 6to4 embutindo 10.0.0.1
    ],
)
def test_proxy_recusa_ipv4_mapeado_e_nao_globais(ip: str) -> None:
    proxy = _carregar("infra/proxy-egresso/proxy.py", "proxy_egresso")
    assert proxy._publico(ip) is False


def test_proxy_aceita_ip_publico_inclusive_mapeado() -> None:
    proxy = _carregar("infra/proxy-egresso/proxy.py", "proxy_egresso2")
    assert proxy._publico("93.184.216.34") and proxy._publico("::ffff:93.184.216.34")


# ---------- achado 7: ponte do CDP ----------


def test_ponte_so_aceita_rede_de_controle_e_falha_fechada() -> None:
    ponte = _carregar("infra/scripts/ponte-cdp.py", "ponte_cdp")
    assert ponte.cliente_permitido("10.213.77.5", "10.213.77.0/24")
    assert ponte.cliente_permitido("127.0.0.1", "10.213.77.0/24")  # healthcheck local
    assert not ponte.cliente_permitido("10.213.78.5", "10.213.77.0/24")  # rede isolada
    assert not ponte.cliente_permitido("10.213.77.5", "")  # sem configuração, ninguém entra
    assert not ponte.cliente_permitido("lixo", "10.213.77.0/24")


def test_ponte_reescreve_websocket_em_json_e_lista() -> None:
    ponte = _carregar("infra/scripts/ponte-cdp.py", "ponte_cdp2")
    alvo = {
        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/AB",
        "devtoolsFrontendUrl": "/devtools/inspector.html?ws=127.0.0.1:9222/devtools/page/AB",
        "id": "AB",
    }
    lista = ponte.reescrever_ws([alvo])
    assert lista[0]["webSocketDebuggerUrl"] == "ws://navegador:9223/devtools/page/AB"
    assert "devtoolsFrontendUrl" not in lista[0]
    for caminho in ("/json", "/json/", "/json/list", "/json/version/", "/json/new?x"):
        assert ponte.caminho_do_pedido(f"GET {caminho} HTTP/1.1".encode()) in ponte.CAMINHOS_COM_WS
