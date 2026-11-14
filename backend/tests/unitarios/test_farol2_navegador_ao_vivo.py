"""Farol-2, item 18: navegador do bot ao vivo, provado com Chromium REAL.

Real: Playwright, Chromium, ``MotorPlaywright``, ``GerenteAbas`` e ``NavegadorAoVivo`` (os dois
laços: quadros e pedidos do usuário). Preparado: um site local, ``*.test`` → 127.0.0.1, a guarda
de SSRF desligada (o alvo é loopback; ela tem testes próprios) e um Redis em memória.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest

from app.eventos.equipe import publicar_evento_equipe
from app.eventos.streams import canal_usuario
from app.ferramentas.base import ErroFerramenta
from app.navegador import perfis as pf
from app.navegador.abas import Aba, GerenteAbas
from app.navegador.ao_vivo import (
    CHAVE_ASSISTINDO,
    CHAVE_ASSUMIDA,
    CHAVE_CAPTURA,
    CHAVE_DONO,
    FILA_COMANDOS,
    QUADROS_RETIDOS,
    Comando,
    NavegadorAoVivo,
    converter_ponto,
    enfileirar_comando,
    marcar_assistindo,
    validar_comando,
)
from app.navegador.persistente import MotorPlaywright

pytestmark = pytest.mark.filterwarnings("ignore")

SEGREDO = "S3nh@-Muito-Secreta-9"
FRASE = "Olá mundo ao vivo"

PAGINA = """<!doctype html><meta charset=utf-8><title>inicio</title>
<style>body{margin:0;font:20px sans-serif}
#b{position:absolute;left:100px;top:100px;width:200px;height:60px}
#t{position:absolute;left:100px;top:200px;width:300px;height:30px}
#s{position:absolute;left:100px;top:260px;width:300px;height:30px}
#a{position:absolute;left:100px;top:320px}</style>
<button id=b onclick="document.title='clicou'">Clique</button>
<input id=t><input id=s type=password>
<a id=a href="http://outro.test/">sair</a>
<script>document.body.addEventListener('keydown',e=>{if(e.key==='Escape')document.title='esc'})</script>
"""


class _Site(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        corpo = PAGINA.encode()
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


async def _sem_guarda(_url: str) -> None:
    return None


class _Kit:
    def __init__(self, motor: MotorPlaywright, gerente: GerenteAbas, porta: int) -> None:
        self.motor, self.gerente, self.porta = motor, gerente, porta
        self.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        self.salvas: list[Aba] = []
        self.usuario, self.agente = uuid4(), uuid4()
        self.instantes: list[float] = []
        """Quando cada quadro foi publicado (o stream só guarda os últimos)."""

        async def publicar(evento: Any, usuario_id: UUID) -> str | None:
            self.instantes.append(time.monotonic())
            return await publicar_evento_equipe(self.redis, evento, usuario_id)

        async def salvar(aba: Aba) -> None:
            self.salvas.append(aba)

        self.vivo = NavegadorAoVivo(
            gerente=gerente, motor=motor, redis=self.redis, publicar=publicar, salvar_aba=salvar
        )

    async def abrir(self) -> Aba:
        return await self.gerente.abrir(
            usuario_id=self.usuario,
            agente_id=self.agente,
            escolha=pf.EscolhaPerfil(),
            url=f"http://alpha.test:{self.porta}/",
        )

    async def eventos(self) -> list[dict[str, Any]]:
        entradas = await self.redis.xrange(canal_usuario(self.usuario))
        return [json.loads(campos["data"]) for _id, campos in entradas]

    async def titulo(self, aba: Aba) -> str:
        return await self.motor.pagina(aba).title()

    async def valor(self, aba: Aba, seletor: str) -> str:
        return await self.motor.pagina(aba).input_value(seletor)

    async def pedir(self, aba: Aba, **campos: Any) -> bool:
        comando = Comando(usuario_id=self.usuario, **campos)
        validar_comando(comando)
        await enfileirar_comando(self.redis, aba.id, comando)
        bruto = await self.redis.lpop(FILA_COMANDOS.format(aba_id=aba.id))
        return await self.vivo.executar(aba.id, bruto)


@pytest.fixture
async def kit(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Kit]:
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    monkeypatch.setattr("app.navegador.persistente.validar_destino", _sem_guarda)
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    p = await async_playwright().start()
    try:
        navegador = await p.chromium.launch(
            executable_path=_chromium(),
            args=["--host-resolver-rules=MAP *.test 127.0.0.1"],
        )
    except Exception as erro:
        await p.stop()
        servidor.shutdown()
        pytest.skip(f"Chromium indisponível: {type(erro).__name__}")

    async def ler(_particao: str) -> dict[str, Any] | None:
        return None

    async def gravar(_particao: str, _estado: dict[str, Any]) -> None:
        return None

    motor = MotorPlaywright(ler_estado=ler, gravar_estado=gravar, ao_console=lambda *_a: None)
    motor._playwright, motor._navegador = p, navegador
    kit = _Kit(motor, GerenteAbas(motor), servidor.server_address[1])
    try:
        yield kit
    finally:
        await kit.vivo.parar()
        await navegador.close()
        await p.stop()
        servidor.shutdown()


# ---------- quadros ----------


async def test_quadro_publica_miniatura_e_guarda_a_captura_com_dono(kit: _Kit) -> None:
    aba = await kit.abrir()
    await kit.vivo.quadro(aba)
    (evento,) = await kit.eventos()
    assert evento["aba_id"] == str(aba.id) and evento["agente_id"] == str(kit.agente)
    assert (evento["largura"], evento["altura"]) == (1280, 720)
    assert evento["mudou"] is True and evento["assumida_pelo_usuario"] is False
    assert evento["miniatura"].startswith("data:image/jpeg;base64,")
    assert evento["titulo"] == "inicio"
    # a captura inteira (para a rota) e o dono ficam no Redis, com prazo
    guardada = await kit.redis.get(CHAVE_CAPTURA.format(aba_id=aba.id))
    assert guardada and await kit.redis.get(CHAVE_DONO.format(aba_id=aba.id)) == str(kit.usuario)
    assert 0 < await kit.redis.ttl(CHAVE_CAPTURA.format(aba_id=aba.id)) <= 120
    # segundo quadro sem mudança: mantém o ritmo, mas sem miniatura
    await kit.vivo.quadro(aba)
    segundo = (await kit.eventos())[-1]
    assert segundo["mudou"] is False and segundo["miniatura"] is None


async def test_so_captura_enquanto_alguem_assiste_e_pelo_menos_1_por_segundo(kit: _Kit) -> None:
    aba = await kit.abrir()
    kit.vivo.iniciar()
    await asyncio.sleep(2.2)
    assert await kit.eventos() == []  # ninguém assistindo: nenhuma captura
    assert await kit.redis.get(CHAVE_CAPTURA.format(aba_id=aba.id)) is None

    await marcar_assistindo(kit.redis, kit.agente)
    assert 0 < await kit.redis.ttl(CHAVE_ASSISTINDO.format(agente_id=kit.agente)) <= 12
    inicio = time.monotonic()
    while time.monotonic() - inicio < 5.0:
        await marcar_assistindo(kit.redis, kit.agente)  # o app renova a cada poucos segundos
        await asyncio.sleep(0.5)
    # 5 s assistindo: um quadro a cada menos de 1 s (o primeiro pode levar até 1 s para sair)
    assert len(kit.instantes) >= 5, len(kit.instantes)
    intervalos = [b - a for a, b in zip(kit.instantes, kit.instantes[1:], strict=False)]
    assert max(intervalos) < 1.0, intervalos
    # o stream do usuário não cresce sem parar: só os últimos quadros ficam
    assert len(await kit.eventos()) <= QUADROS_RETIDOS

    # parou de assistir (a marca expira): os quadros param
    await kit.redis.delete(CHAVE_ASSISTINDO.format(agente_id=kit.agente))
    await asyncio.sleep(1.2)
    ids = await kit.redis.xrange(canal_usuario(kit.usuario))
    await asyncio.sleep(2.0)
    assert await kit.redis.xrange(canal_usuario(kit.usuario)) == ids


async def test_escolhe_a_aba_assumida_e_ignora_bot_que_ninguem_assiste(kit: _Kit) -> None:
    primeira = await kit.abrir()
    segunda = await kit.abrir()
    outro = uuid4()
    await kit.gerente.abrir(
        usuario_id=kit.usuario, agente_id=outro, escolha=pf.EscolhaPerfil(), url=None
    )
    await marcar_assistindo(kit.redis, kit.agente)
    assert [a.id for a in await kit.vivo.abas_assistidas()] == [segunda.id]  # a mais recente
    await kit.redis.set(CHAVE_ASSUMIDA.format(aba_id=primeira.id), "1")
    assert [a.id for a in await kit.vivo.abas_assistidas()] == [primeira.id]  # a assumida


# ---------- o usuário age na aba assumida ----------


async def test_clique_na_escala_da_imagem_vira_clique_real(kit: _Kit) -> None:
    aba = await kit.abrir()
    # o botão ocupa (100,100)-(300,160) na janela de 1280x720; numa imagem de 640x360 está em
    # (50,50)-(150,80): o centro é (100,65)
    assert converter_ponto(100, 65, 640, 360, (1280, 720)) == (200.0, 130.0)

    # sem assumir, nada acontece (e a ordem é descartada em silêncio)
    assert await kit.pedir(aba, tipo="clicar", x=100, y=65, largura=640, altura=360) is False
    assert await kit.titulo(aba) == "inicio"

    await kit.redis.set(CHAVE_ASSUMIDA.format(aba_id=aba.id), "1")
    assert await kit.pedir(aba, tipo="clicar", x=100, y=65, largura=640, altura=360) is True
    assert await kit.titulo(aba) == "clicou"
    # o quadro de resposta já saiu, mostrando que a aba está assumida
    ultimo = (await kit.eventos())[-1]
    assert ultimo["assumida_pelo_usuario"] is True and ultimo["titulo"] == "clicou"
    # o registro da aba foi atualizado e salvo
    assert kit.salvas and kit.salvas[-1].titulo == "clicou"


async def test_digitar_nunca_vai_para_evento_estado_log_nem_fila(
    kit: _Kit, caplog: pytest.LogCaptureFixture
) -> None:
    aba = await kit.abrir()
    await kit.redis.set(CHAVE_ASSUMIDA.format(aba_id=aba.id), "1")
    caplog.set_level(logging.DEBUG)
    # campo de texto e campo de senha (clique na imagem 640x360, depois digita)
    await kit.pedir(aba, tipo="clicar", x=100, y=107, largura=640, altura=360)  # (200,214)
    assert await kit.pedir(aba, tipo="digitar", texto=FRASE) is True
    assert await kit.valor(aba, "#t") == FRASE
    await kit.pedir(aba, tipo="clicar", x=100, y=137, largura=640, altura=360)  # (200,274)
    assert await kit.pedir(aba, tipo="digitar", texto=SEGREDO) is True
    assert await kit.valor(aba, "#s") == SEGREDO  # a senha chegou ao campo, de verdade

    for texto in (FRASE, SEGREDO):
        tudo = json.dumps(await kit.eventos()) + " ".join(r.getMessage() for r in caplog.records)
        assert texto not in tudo
        # nem em chave nenhuma do Redis (estado, fila); a captura é imagem em base64
        for chave in await kit.redis.keys("*"):
            if chave.startswith("navegador:captura:") or await kit.redis.type(chave) != "string":
                continue
            assert texto not in (await kit.redis.get(chave) or ""), chave
    assert await kit.redis.llen(FILA_COMANDOS.format(aba_id=aba.id)) == 0
    assert SEGREDO not in repr(Comando(tipo="digitar", usuario_id=kit.usuario, texto=SEGREDO))


async def test_teclas_e_rolagem_so_da_lista_e_so_do_dono(kit: _Kit) -> None:
    aba = await kit.abrir()
    await kit.redis.set(CHAVE_ASSUMIDA.format(aba_id=aba.id), "1")
    assert await kit.pedir(aba, tipo="tecla", tecla="Escape") is True
    assert await kit.titulo(aba) == "esc"
    with pytest.raises(ErroFerramenta, match="Tecla não permitida"):
        validar_comando(Comando(tipo="tecla", usuario_id=kit.usuario, tecla="Control+w"))
    assert await kit.pedir(aba, tipo="rolar", dy=300) is True

    # pedido de outro usuário na mesma aba é descartado
    intruso = Comando(tipo="clicar", usuario_id=uuid4(), x=100, y=65, largura=640, altura=360)
    assert await kit.vivo.executar(aba.id, intruso.model_dump_json()) is False
    # lixo na fila também
    assert await kit.vivo.executar(aba.id, "{nao e json") is False
    assert await kit.vivo.executar(uuid4(), intruso.model_dump_json()) is False


async def test_laco_de_pedidos_executa_o_que_a_api_enfileirou(kit: _Kit) -> None:
    aba = await kit.abrir()
    await kit.redis.set(CHAVE_ASSUMIDA.format(aba_id=aba.id), "1")
    kit.vivo.iniciar()
    await enfileirar_comando(
        kit.redis,
        aba.id,
        Comando(tipo="clicar", usuario_id=kit.usuario, x=100, y=65, largura=640, altura=360),
    )
    for _ in range(40):
        if await kit.titulo(aba) == "clicou":
            break
        await asyncio.sleep(0.1)
    assert await kit.titulo(aba) == "clicou"


async def test_devolver_solta_a_aba_e_o_bot_volta_a_usar(kit: _Kit) -> None:
    from app.ferramentas.navegador_worker import AmbienteNavegador

    aba = await kit.abrir()
    ambiente = AmbienteNavegador(
        gerente=kit.gerente,
        motor=kit.motor,
        arvore=None,  # type: ignore[arg-type]
        repositorio=None,  # type: ignore[arg-type]
        sessoes=None,
        redis=kit.redis,
    )
    # o usuário assume (a API grava a marca) e a ferramenta do bot percebe e recua
    await kit.redis.set(CHAVE_ASSUMIDA.format(aba_id=aba.id), "1")
    aba = await ambiente._sincronizar_assuncao(aba)
    assert aba.assumida_pelo_usuario
    with pytest.raises(ErroFerramenta, match="usuário está usando"):
        kit.gerente.exigir(aba.id, kit.agente)
    # devolver: os pedidos do usuário param e o bot retoma
    await kit.redis.delete(CHAVE_ASSUMIDA.format(aba_id=aba.id))
    assert await kit.pedir(aba, tipo="clicar", x=100, y=65, largura=640, altura=360) is False
    aba = await ambiente._sincronizar_assuncao(aba)
    assert not aba.assumida_pelo_usuario
    assert kit.gerente.exigir(aba.id, kit.agente).id == aba.id
    assert (await kit.gerente.usar(aba.id, kit.agente)).id == aba.id


def test_validacao_do_clique_e_da_rolagem() -> None:
    usuario = uuid4()
    for ruim in (
        {"tipo": "clicar", "x": 1, "y": 1},  # sem o tamanho da imagem
        {"tipo": "clicar", "x": 700, "y": 1, "largura": 640, "altura": 360},  # fora da imagem
        {"tipo": "digitar"},
        {"tipo": "rolar", "dy": 0},
    ):
        with pytest.raises(ErroFerramenta):
            validar_comando(Comando(usuario_id=usuario, **ruim))


async def test_aba_fechada_nao_deixa_nada_guardado_na_memoria(kit: _Kit) -> None:
    aba = await kit.abrir()
    await kit.vivo.quadro(aba)
    assert aba.id in kit.vivo._ids and aba.id in kit.vivo._ultimo_quadro
    await kit.gerente.fechar(aba.id, kit.agente)
    kit.vivo._esquecer_fechadas()
    assert aba.id not in kit.vivo._ids and aba.id not in kit.vivo._ultimo_quadro
