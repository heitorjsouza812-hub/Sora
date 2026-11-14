"""Farol-2, item 1, com o contêiner de verdade: a mensagem que chega ao modelo leva a imagem
da tela do computador do bot, na escala certa, e só a última.

Usa o computador virtual real (``infra/computador``), o ``ServicoComputador`` real e um agente do
LangChain; o modelo é um gravador que guarda o que recebe (não há chave nem rede).
"""

from __future__ import annotations

import base64
import io
import subprocess
from typing import Any
from uuid import uuid4

import fakeredis.aioredis
import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from PIL import Image

from app.computador.interface import AcaoComputador, Alvo
from app.computador.pc_usuario import ProvedorPcUsuario
from app.computador.servico import ServicoComputador
from app.computador.virtual import (
    NOME_PROXY,
    REDE_SAIDA,
    ClienteDocker,
    GerenteComputadoresDocker,
    nome_do_computador,
)
from app.computador.visao import COM_VISAO, MiddlewareVisaoTela
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from tests.unitarios.test_farol2_visao import _chamada, _Gravador

pytestmark = pytest.mark.integracao

IMAGEM = "sora-computador:1"
IMAGEM_PROXY = "sora-proxy-egresso:1"


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=False)


@pytest.fixture(scope="module", autouse=True)
def _imagens():
    for imagem in (IMAGEM, IMAGEM_PROXY):
        if _docker("image", "inspect", imagem).returncode != 0:
            pytest.skip(f"imagem {imagem} não construída (veja docs/computador-por-bot.md)")
    yield
    _docker("rm", "-f", NOME_PROXY)
    _docker("network", "rm", REDE_SAIDA)


async def test_a_mensagem_ao_modelo_leva_a_imagem_da_tela_real() -> None:
    gerente = GerenteComputadoresDocker(ClienteDocker(), imagem=IMAGEM, imagem_proxy=IMAGEM_PROXY)

    async def publicar(_e: Any, _u: Any) -> None:
        return None

    servico = ServicoComputador(
        provedores={Alvo.VIRTUAL: gerente, Alvo.PC_USUARIO: ProvedorPcUsuario()},
        redis=fakeredis.aioredis.FakeRedis(),
        publicar=publicar,
    )
    ctx = ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4())

    async def computador_observar() -> str:
        return await servico.observar(ctx)

    async def computador_agir() -> str:
        return await servico.agir(ctx, [AcaoComputador(tipo="abrir", programa="terminal")])

    ferramentas = [
        StructuredTool.from_function(
            coroutine=computador_observar, name="computador_observar", description="Olha."
        ),
        StructuredTool.from_function(
            coroutine=computador_agir, name="computador_agir", description="Abre o terminal."
        ),
    ]
    modelo = _Gravador(
        roteiro=[
            _chamada("computador_observar", {}, "a"),
            _chamada("computador_agir", {}, "b"),
            AIMessage(content="pronto"),
        ]
    )
    agente = create_agent(
        model=modelo,
        tools=ferramentas,
        system_prompt="Você é um bot.",
        middleware=[
            MiddlewareVisaoTela(ctx.agente_id, servico=lambda: servico, tem_visao=lambda _m: True)
        ],
    )
    try:
        await agente.ainvoke({"messages": [HumanMessage("abra o terminal")]})
        # a 1ª chamada ainda não viu tela; a 2ª e a 3ª recebem UMA imagem cada
        contagens = []
        for vistos in modelo.vistos:
            blocos = [
                b
                for m in vistos
                if isinstance(m.content, list)
                for b in m.content
                if b.get("type") == "image_url"
            ]
            contagens.append(len(blocos))
        assert contagens == [0, 1, 1]

        ultima = modelo.vistos[-1][-1]
        assert isinstance(ultima, HumanMessage)
        texto, bloco = ultima.content
        assert "leitura @c2" in texto["text"] and "1280x800" in texto["text"]
        assert "escala 1:1" in texto["text"]
        url = bloco["image_url"]["url"]
        assert url.startswith("data:image/")
        with Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))) as figura:
            assert figura.size == (1280, 800)
        assert COM_VISAO in modelo.vistos[-1][0].content
        # as duas telas vistas são diferentes: a de depois do clique tem o terminal aberto
        primeira = modelo.vistos[1][-1].content[1]["image_url"]["url"]
        assert primeira != url
    finally:
        nome = nome_do_computador(ctx.agente_id)
        _docker("rm", "-f", nome)
        _docker("network", "disconnect", "-f", nome, NOME_PROXY)
        _docker("network", "rm", nome)


async def test_entregar_arquivo_do_computador_real_vira_anexo_e_recusa_o_grande() -> None:
    gerente = GerenteComputadoresDocker(ClienteDocker(), imagem=IMAGEM, imagem_proxy=IMAGEM_PROXY)
    guardados: list[tuple[str, bytes]] = []

    async def publicar(_e: Any, _u: Any) -> None:
        return None

    async def guardar(_ctx: ContextoFerramenta, nome: str, dados: bytes):
        guardados.append((nome, dados))
        return uuid4()

    servico = ServicoComputador(
        provedores={Alvo.VIRTUAL: gerente, Alvo.PC_USUARIO: ProvedorPcUsuario()},
        redis=fakeredis.aioredis.FakeRedis(),
        publicar=publicar,
        guardar_anexo=guardar,
    )
    ctx = ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4())
    nome = nome_do_computador(ctx.agente_id)
    try:
        await servico.escrever(ctx, "relatorios/maio.csv", "produto;café\nlatte;12\n")
        resposta = await servico.entregar(ctx, "relatorios/maio.csv")
        assert guardados == [("maio.csv", "produto;café\nlatte;12\n".encode())]
        assert "anexo_id" in resposta
        # arquivo binário de verdade, byte a byte (30 KB aleatórios gerados dentro do computador)
        criado = _docker(
            "exec", nome, "bash", "-c", "head -c 30000 /dev/urandom > /home/bot/arquivos/x.bin"
        )
        assert criado.returncode == 0, criado.stderr
        await servico.entregar(ctx, "x.bin")
        assert len(guardados[-1][1]) == 30000
        lido = _docker("exec", nome, "sha256sum", "/home/bot/arquivos/x.bin").stdout.split()[0]
        import hashlib

        assert hashlib.sha256(guardados[-1][1]).hexdigest() == lido
        # arquivo grande demais é recusado sem copiar tudo
        grande = _docker(
            "exec", nome, "bash", "-c", "head -c 11534336 /dev/zero > /home/bot/arquivos/g.bin"
        )
        assert grande.returncode == 0, grande.stderr
        with pytest.raises(ErroFerramenta, match="passa de 10 MB"):
            await servico.entregar(ctx, "g.bin")
        # fora da área não entrega nada
        with pytest.raises(ErroFerramenta):
            await servico.entregar(ctx, "../.bashrc")
    finally:
        _docker("rm", "-f", nome)
        _docker("network", "disconnect", "-f", nome, NOME_PROXY)
        _docker("network", "rm", nome)
