"""Chave: segurança por ferramenta sem banco nem rede (SSRF, esquemas, PC do usuário, saída)."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.busca.ler_pagina import EnderecoBloqueado, ErroLeitura, validar_destino, validar_url
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta

ENDERECOS_INTERNOS = [
    "http://127.0.0.1/",
    "http://localhost/",
    "http://0.0.0.0/",
    "http://10.1.2.3/",
    "http://172.16.0.1/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://100.64.0.1/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[fe80::1]/",
    "http://[fd00::1]/",
    "http://2130706433/",  # 127.0.0.1 em decimal
    "http://0x7f000001/",  # 127.0.0.1 em hexadecimal
    "http://127.1/",
    "http://0177.0.0.1/",
]


@pytest.mark.parametrize("url", ENDERECOS_INTERNOS)
async def test_ler_pagina_recusa_endereco_interno(url: str) -> None:
    with pytest.raises((EnderecoBloqueado, ErroLeitura)):
        await validar_destino(url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<script>1</script>",
        "ftp://exemplo.com/x",
        "gopher://exemplo.com/",
        "http://usuario:senha@exemplo.com/",
        "https://",
        "",
        "não é url",
    ],
)
def test_ler_pagina_recusa_esquema_e_forma_invalidos(url: str) -> None:
    with pytest.raises((EnderecoBloqueado, ErroLeitura)):
        validar_url(url)


async def test_ler_pagina_entrega_erro_legivel_ao_modelo(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ferramentas import ler_pagina as modulo

    monkeypatch.setattr(modulo, "obter_redis", lambda: None)
    for url in ("http://127.0.0.1/", "file:///etc/passwd", "isso nao e url"):
        with pytest.raises(ErroFerramenta):
            await modulo.ler_pagina(modulo.LerPagina(url=url), _ctx())


def _ctx(**extra) -> ContextoFerramenta:
    return ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4(), **extra)


def test_ler_pagina_url_enorme_e_vazia_sao_recusadas_pelo_esquema() -> None:
    from app.ferramentas.ler_pagina import LerPagina

    with pytest.raises(ValidationError):
        LerPagina(url="")
    with pytest.raises(ValidationError):
        LerPagina(url="https://exemplo.com/" + "a" * 2000)


# ------------------------------------------------------------------ navegador


@pytest.mark.parametrize("url", [*ENDERECOS_INTERNOS[:8], "file:///etc/passwd", "javascript:1"])
async def test_navegador_recusa_destino_interno(url: str) -> None:
    from app.navegador.sessao import validar_destino as _  # noqa: F401  (mesma barreira)

    with pytest.raises((EnderecoBloqueado, ErroLeitura)):
        await validar_destino(httpx.URL(url) if "://" in url else url)


# ------------------------------------------------------------------ computador / PC do usuário


async def test_computador_pc_usuario_nunca_em_rotina_sem_supervisao() -> None:
    from app.computador.ferramentas import (
        ComputadorAbrirPrograma,
        ComputadorAgir,
        ComputadorObservar,
        computador_abrir_programa,
        computador_agir,
        computador_observar,
    )

    rotina = _ctx(sem_supervisao=True)
    with pytest.raises(ErroFerramenta, match="supervis"):
        await computador_observar(ComputadorObservar(alvo="pc_usuario"), rotina)
    with pytest.raises(ErroFerramenta, match="supervis"):
        await computador_agir(
            ComputadorAgir(acoes=[{"tipo": "clicar", "x": 1, "y": 1}], alvo="pc_usuario"), rotina
        )
    with pytest.raises(ErroFerramenta, match="supervis"):
        await computador_abrir_programa(ComputadorAbrirPrograma(programa="Excel"), rotina)


def test_computador_abrir_programa_so_aceita_a_lista_fechada() -> None:
    from app.computador.ferramentas import ComputadorAbrirPrograma

    for ruim in ("cmd", "powershell", "Terminal", "regedit", "C:/Windows/System32/cmd.exe"):
        with pytest.raises(ValidationError):
            ComputadorAbrirPrograma(programa=ruim)
    with pytest.raises(ValidationError):
        ComputadorAbrirPrograma(programa="Excel", alvo="virtual")


def test_computador_alvo_desconhecido_e_acoes_demais_sao_recusados() -> None:
    from app.computador.ferramentas import ComputadorAgir, ComputadorObservar

    with pytest.raises(ValidationError):
        ComputadorObservar(alvo="servidor")
    with pytest.raises(ValidationError):
        ComputadorAgir(acoes=[])
    with pytest.raises(ValidationError):
        ComputadorAgir(acoes=[{"tipo": "clicar", "x": 1, "y": 1}] * 50)


@pytest.mark.parametrize(
    "ruim", ["../x", "/etc/passwd", "a/../../b", "a\x00b", "..\\x", "a\\..\\b"]
)
async def test_computador_arquivos_recusa_caminho_fora_da_area(ruim: str) -> None:
    from app.computador.interface import caminho_relativo

    try:
        resultado = caminho_relativo(ruim)
    except ErroFerramenta:
        return

    assert ".." not in resultado.split("/") and not resultado.startswith("/")


async def test_computador_pc_usuario_nao_lista_nem_le_nem_escreve_arquivos() -> None:
    from app.computador.pc_usuario import ComputadorPcUsuario

    pc = ComputadorPcUsuario.__new__(ComputadorPcUsuario)
    with pytest.raises(ErroFerramenta):
        await pc.listar_arquivos("")
    with pytest.raises(ErroFerramenta):
        await pc.ler_arquivo("C:/Users/x/segredo.txt", 100)
    with pytest.raises(ErroFerramenta):
        await pc.escrever_arquivo("C:/Users/x/a.txt", b"x")


async def test_canal_historico_em_canal_longo_devolve_as_ultimas_e_respeita_antes_de_seq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O serviço pagina de 200 em 200, das mais antigas para as mais novas: ler só a primeira
    página mostrava o começo do canal e escondia as mensagens recentes."""
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from app.canais_equipe import execucao
    from app.canais_equipe.ferramentas import CanalHistorico

    total = 450
    todas = [
        SimpleNamespace(seq=n, autor=SimpleNamespace(value="agente"), texto=f"m{n}")
        for n in range(1, total + 1)
    ]

    class ServicoFalso:
        def __init__(self, _armazem) -> None: ...

        async def historico(self, canal_id, usuario_id, *, depois_de_seq=0, limite=50):
            return [m for m in todas if m.seq > depois_de_seq][: min(limite, 200)]

    @asynccontextmanager
    async def sessao_falsa():
        yield None

    monkeypatch.setattr(execucao, "ServicoCanais", ServicoFalso)
    monkeypatch.setattr(execucao, "ArmazemCanaisSQL", lambda _s: None)
    monkeypatch.setattr(execucao, "fabrica_sessoes", lambda: sessao_falsa)
    contexto = _ctx(canal_id=uuid4(), tarefa_canal_id=uuid4(), revisao_canal=1)

    ultimas = await execucao.canal_historico(CanalHistorico(limite=3), contexto)
    assert ultimas.splitlines() == [
        "[448] agente: m448",
        "[449] agente: m449",
        "[450] agente: m450",
    ]
    antes = await execucao.canal_historico(CanalHistorico(antes_de_seq=300, limite=2), contexto)
    assert antes.splitlines() == ["[298] agente: m298", "[299] agente: m299"]
