"""C2 (Farol): computador virtual por bot com Docker de verdade.

Liga o contêiner do bot (``infra/computador``), observa, age e confere; grava e lê na área de
arquivos; prova o isolamento (raiz só leitura, sem capacidades, sem nada do host, rede interna
só do bot com saída pelo proxy que recusa IP privado); dois bots em paralelo sem se enxergarem;
e o desligamento por ociosidade. Precisa das imagens ``sora-computador:1`` e
``sora-proxy-egresso:1`` (``docker build``; veja ``docs/computador-por-bot.md``).
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest

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
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta

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


class _Kit:
    def __init__(self) -> None:
        self.gerente = GerenteComputadoresDocker(
            ClienteDocker(), imagem=IMAGEM, imagem_proxy=IMAGEM_PROXY
        )
        self.eventos: list = []

        async def publicar(evento, _usuario) -> None:
            self.eventos.append(evento)

        self.servico = ServicoComputador(
            provedores={Alvo.VIRTUAL: self.gerente, Alvo.PC_USUARIO: ProvedorPcUsuario()},
            redis=fakeredis.aioredis.FakeRedis(),
            publicar=publicar,
        )
        self.agentes: list[UUID] = []

    def ctx(self) -> ContextoFerramenta:
        agente = uuid4()
        self.agentes.append(agente)
        return ContextoFerramenta(usuario_id=uuid4(), agente_id=agente, conversa_id=uuid4())


@pytest.fixture
def kit():
    kit = _Kit()
    yield kit
    for agente in kit.agentes:
        nome = nome_do_computador(agente)
        _docker("rm", "-f", nome)
        _docker("network", "disconnect", "-f", nome, NOME_PROXY)
        _docker("network", "rm", nome)


def _dentro(nome: str, script: str) -> subprocess.CompletedProcess[str]:
    """Só o teste usa shell dentro do contêiner (para provar o isolamento)."""
    return _docker("exec", nome, "bash", "-c", script)


async def test_liga_observa_age_confere_e_mexe_nos_arquivos(kit: _Kit) -> None:
    ctx = kit.ctx()
    texto = await kit.servico.observar(ctx)
    assert "Chromium" in texto and "@c1:j1" in texto and "1280x800" in texto

    await kit.servico.agir(ctx, [AcaoComputador(tipo="abrir", programa="terminal")])
    await asyncio.sleep(1.0)  # o xterm aparece depois do clique
    leitura = await kit.servico.observar(ctx)
    assert "computador" in leitura  # título do terminal (bot@computador)
    resultado = await kit.servico.agir(
        ctx,
        [
            AcaoComputador(tipo="digitar", texto="echo ola-sora > arquivos/prova.txt"),
            AcaoComputador(tipo="tecla", tecla="Enter"),
        ],
    )
    assert "2 de 2" in resultado and "a tela mudou" in resultado
    assert kit.eventos[-1].mudou is True and kit.eventos[-1].miniatura
    assert "ola-sora" not in kit.eventos[-1].model_dump_json()

    lido = await kit.servico.arquivos(ctx, "ler", "prova.txt")
    assert "ola-sora" in lido
    await kit.servico.escrever(ctx, "notas/hoje.txt", "café com leite")
    listagem = await kit.servico.arquivos(ctx, "listar", "")
    assert "prova.txt" in listagem and "notas/hoje.txt" in listagem
    assert "café com leite" in await kit.servico.arquivos(ctx, "ler", "notas/hoje.txt")

    # link simbólico para fora da área não vaza nada
    nome = nome_do_computador(ctx.agente_id)
    assert _dentro(nome, "ln -s /etc/passwd /home/bot/arquivos/fuga").returncode == 0
    with pytest.raises(ErroFerramenta, match="sai da sua área"):
        await kit.servico.arquivos(ctx, "ler", "fuga")
    with pytest.raises(ErroFerramenta, match="sai da sua área"):
        await kit.servico.escrever(ctx, "fuga", "x")
    with pytest.raises(ErroFerramenta):
        await kit.servico.arquivos(ctx, "ler", "../.bashrc")

    # reaproveitado entre turnos: o mesmo contêiner, sem religar
    inicio = _docker("inspect", "--format", "{{.State.StartedAt}}", nome).stdout
    await kit.servico.observar(ctx)
    assert _docker("inspect", "--format", "{{.State.StartedAt}}", nome).stdout == inicio


async def test_conteiner_isolado(kit: _Kit) -> None:
    ctx = kit.ctx()
    await kit.servico.observar(ctx)
    nome = nome_do_computador(ctx.agente_id)
    dados = json.loads(_docker("inspect", nome).stdout)[0]
    host = dados["HostConfig"]
    assert host["ReadonlyRootfs"] is True
    assert host["CapDrop"] == ["ALL"]
    assert "no-new-privileges" in host["SecurityOpt"]
    assert host["Privileged"] is False
    assert host["Memory"] == 1024**3 and host["NanoCpus"] == 10**9 and host["PidsLimit"] == 512
    assert dados["Mounts"] == [] and not host.get("Binds")
    assert dados["Config"]["User"] == "1000:1000"
    assert set(dados["NetworkSettings"]["Networks"]) == {nome}
    rede = json.loads(_docker("network", "inspect", nome).stdout)[0]
    assert rede["Internal"] is True

    # raiz só leitura e sem root
    assert _dentro(nome, "touch /etc/x").returncode != 0
    assert _dentro(nome, "id -u").stdout.strip() == "1000"
    # sem saída direta: só o proxy
    direto = _dentro(nome, "timeout 5 bash -c 'exec 3<>/dev/tcp/1.1.1.1/53' && echo ABRIU")
    assert "ABRIU" not in direto.stdout
    # o proxy recusa IP privado (depois do DNS) e endereço de metadados da nuvem
    for alvo in ("10.0.0.5:80", "169.254.169.254:80", "127.0.0.1:3128"):
        resposta = _dentro(
            nome,
            "exec 3<>/dev/tcp/sora-proxy/3128; "
            f"printf 'CONNECT {alvo} HTTP/1.1\\r\\nHost: {alvo}\\r\\n\\r\\n' >&3; "
            "timeout 5 head -c 40 <&3",
        )
        assert "403" in resposta.stdout, (alvo, resposta.stdout, resposta.stderr)
    # e deixa passar a internet pública (se este host tiver internet)
    try:
        socket.create_connection(("example.com", 443), 5).close()
    except OSError:
        return
    publico = _dentro(
        nome,
        "exec 3<>/dev/tcp/sora-proxy/3128; "
        "printf 'CONNECT example.com:443 HTTP/1.1\\r\\nHost: example.com\\r\\n\\r\\n' >&3; "
        "timeout 10 head -c 12 <&3",
    )
    assert publico.stdout.endswith(" 200"), publico.stdout


async def test_dois_bots_em_paralelo_nao_se_enxergam(kit: _Kit) -> None:
    a, b = kit.ctx(), kit.ctx()
    await asyncio.gather(kit.servico.observar(a), kit.servico.observar(b))
    nome_a, nome_b = nome_do_computador(a.agente_id), nome_do_computador(b.agente_id)
    ip_b = json.loads(_docker("inspect", nome_b).stdout)[0]["NetworkSettings"]["Networks"][nome_b][
        "IPAddress"
    ]
    assert _dentro(nome_a, f"getent hosts {nome_b}").returncode != 0
    sonda = _dentro(nome_a, f"timeout 3 bash -c 'exec 3<>/dev/tcp/{ip_b}/22' && echo ABRIU")
    assert "ABRIU" not in sonda.stdout

    # agindo ao mesmo tempo, cada um no seu computador
    await asyncio.gather(
        kit.servico.escrever(a, "quem.txt", "A"), kit.servico.escrever(b, "quem.txt", "B")
    )
    assert "A" in await kit.servico.arquivos(a, "ler", "quem.txt")
    assert "B" in await kit.servico.arquivos(b, "ler", "quem.txt")


async def test_desliga_por_ociosidade(kit: _Kit) -> None:
    ctx = kit.ctx()
    await kit.servico.observar(ctx)
    nome = nome_do_computador(ctx.agente_id)
    assert ctx.agente_id in await kit.gerente.ligados()
    # usado agora: fica
    assert ctx.agente_id not in await kit.gerente.desligar_ociosos({ctx.agente_id: 9e12}, 60)
    # sem uso: sai, e a rede dele também
    assert ctx.agente_id in await kit.gerente.desligar_ociosos({}, 60)
    assert _docker("inspect", nome).returncode != 0
    assert _docker("network", "inspect", nome).returncode != 0
