"""Alvo ``virtual``: um contêiner Linux por bot, com tela (Xvfb), Openbox, Chromium e arquivos.

Imagem em ``infra/computador/Dockerfile``. O worker cria o contêiner na primeira ação do bot,
reaproveita entre turnos e desliga por ociosidade (``desligar_ociosos``). Regras de isolamento
(as mesmas do ``executar_comando``, mais as da tela):

- em produção só roda com host Docker separado (``SANDBOX_DOCKER_HOST``);
- raiz só leitura, sem capacidades, ``no-new-privileges``, usuário 1000, limite de memória, CPU
  e processos; a escrita só vai para ``tmpfs`` com tamanho (área do bot e ``/tmp``);
- nada do host é montado;
- rede interna **só do bot** (``--internal``), cuja única porta de saída é o proxy de egresso
  (``infra/proxy-egresso``: recusa IP privado depois do DNS). Bots não se enxergam;
- todo comando é ``docker exec`` com lista de argumentos fixa (sem shell com texto do modelo).

O controle é feito pelo CLI do Docker numa thread (o loop "selector" do worker no Windows não
cria subprocessos assíncronos), como em ``SandboxDocker``.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from uuid import UUID

from app.computador.interface import (
    AcaoResolvida,
    Alvo,
    ArquivoArea,
    Janela,
    Observacao,
    Tela,
    caminho_relativo,
)
from app.ferramentas.base import ErroFerramenta

registro = logging.getLogger(__name__)

PREFIXO = "sora-pc-"
NOME_PROXY = "sora-pc-proxy"
REDE_SAIDA = "sora-pc-saida"
ALIAS_PROXY = "sora-proxy"
PORTA_PROXY = 3128
AREA = "/home/bot/arquivos"
ROTULO = "sora.computador"

MEMORIA = "1g"
CPUS = "1"
MAX_PROCESSOS = 512
TMP_TAMANHO = "256m"
HOME_TAMANHO = "512m"
SHM_TAMANHO = "256m"
PRAZO_COMANDO_S = 30
PRAZO_PRONTO_S = 40
MAX_ARQUIVOS_LISTADOS = 200
MAX_ESCRITA_BYTES = 1024 * 1024


class ErroDocker(ErroFerramenta):
    pass


@dataclass(slots=True)
class ClienteDocker:
    """``docker`` em subprocesso, com ``DOCKER_HOST`` opcional (host separado em produção)."""

    docker: str = "docker"
    docker_host: str | None = None

    def _ambiente(self) -> dict[str, str]:
        ambiente = dict(os.environ)
        if self.docker_host:
            ambiente["DOCKER_HOST"] = self.docker_host
        return ambiente

    def rodar_sync(
        self, *args: str, entrada: bytes | None = None, prazo: float = PRAZO_COMANDO_S
    ) -> subprocess.CompletedProcess[bytes]:
        if shutil.which(self.docker) is None:
            raise ErroDocker("O computador virtual não está disponível neste servidor.")
        try:
            return subprocess.run(
                [self.docker, *args],
                env=self._ambiente(),
                input=entrada,
                stdin=None if entrada is not None else subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=prazo,
            )
        except subprocess.TimeoutExpired as erro:
            raise ErroDocker("O computador virtual demorou demais para responder.") from erro

    async def rodar(
        self, *args: str, entrada: bytes | None = None, prazo: float = PRAZO_COMANDO_S
    ) -> subprocess.CompletedProcess[bytes]:
        return await asyncio.to_thread(self.rodar_sync, *args, entrada=entrada, prazo=prazo)


def nome_do_computador(agente_id: UUID) -> str:
    return f"{PREFIXO}{agente_id.hex}"


def argumentos_do_container(
    *, agente_id: UUID, usuario_id: UUID, imagem: str, tela: str = "1280x800x24"
) -> list[str]:
    """``docker run`` do computador do bot, com tudo travado. Testado em ``test_computador``."""
    nome = nome_do_computador(agente_id)
    return [
        "run",
        "--detach",
        "--init",
        "--name",
        nome,
        "--hostname",
        "computador",
        "--network",
        nome,
        "--memory",
        MEMORIA,
        "--memory-swap",
        MEMORIA,
        "--cpus",
        CPUS,
        "--pids-limit",
        str(MAX_PROCESSOS),
        "--read-only",
        "--tmpfs",
        f"/tmp:rw,nosuid,nodev,size={TMP_TAMANHO}",
        "--tmpfs",
        f"/home/bot:rw,nosuid,nodev,size={HOME_TAMANHO},uid=1000,gid=1000,mode=0700",
        "--shm-size",
        SHM_TAMANHO,
        "--ipc",
        "private",
        "--user",
        "1000:1000",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--env",
        f"SORA_PROXY=http://{ALIAS_PROXY}:{PORTA_PROXY}",
        "--env",
        f"HTTP_PROXY=http://{ALIAS_PROXY}:{PORTA_PROXY}",
        "--env",
        f"HTTPS_PROXY=http://{ALIAS_PROXY}:{PORTA_PROXY}",
        "--env",
        "NO_PROXY=localhost,127.0.0.1",
        "--env",
        f"SORA_TELA={tela}",
        "--label",
        f"{ROTULO}=1",
        "--label",
        f"sora.agente={agente_id}",
        "--label",
        f"sora.usuario={usuario_id}",
        imagem,
    ]


def ler_janelas(saida: str) -> list[Janela]:
    """Saída do ``sora-janelas`` (``wmctrl -lG`` + ``---`` + id da janela ativa em decimal)."""
    lista, _, ativa_txt = saida.partition("---")
    try:
        ativa = int(ativa_txt.strip().splitlines()[0]) if ativa_txt.strip() else None
    except ValueError:
        ativa = None
    janelas: list[Janela] = []
    for linha in lista.splitlines():
        partes = linha.split(None, 7)
        if len(partes) < 7:
            continue
        id_hex, _mesa, x, y, larg, alt = partes[:6]
        titulo = partes[7] if len(partes) > 7 else ""
        try:
            id_int = int(id_hex, 16)
            geo = [int(x), int(y), int(larg), int(alt)]
        except ValueError:
            continue
        if geo[2] <= 1 or geo[3] <= 1:
            continue
        janelas.append(
            Janela(
                id_nativo=id_hex,
                titulo=titulo.strip()[:200],
                x=max(geo[0], 0),
                y=max(geo[1], 0),
                largura=geo[2],
                altura=geo[3],
                ativa=ativa == id_int,
            )
        )
    return janelas


_BOTAO_ROLAGEM = {"cima": "4", "baixo": "5", "esquerda": "6", "direita": "7"}


def comando_xdotool(resolvida: AcaoResolvida) -> list[str]:
    """Argumentos do ``xdotool`` para uma ação já resolvida (nunca passa por shell)."""
    acao = resolvida.acao
    ponto = resolvida.ponto
    mover = ["mousemove", "--sync", str(ponto[0]), str(ponto[1])] if ponto else []
    if acao.tipo == "clicar":
        return ["xdotool", *mover, "click", "1"]
    if acao.tipo == "clique_duplo":
        return ["xdotool", *mover, "click", "--repeat", "2", "--delay", "90", "1"]
    if acao.tipo == "clicar_direito":
        return ["xdotool", *mover, "click", "3"]
    if acao.tipo == "digitar":
        return ["xdotool", "type", "--delay", "18", "--clearmodifiers", "--", acao.texto or ""]
    if acao.tipo == "tecla":
        return ["xdotool", "key", "--clearmodifiers", "--", resolvida.tecla or ""]
    if acao.tipo == "rolar":
        botao = _BOTAO_ROLAGEM[acao.direcao]
        return [
            "xdotool",
            *mover,
            "click",
            "--repeat",
            str(acao.quantidade),
            "--delay",
            "40",
            botao,
        ]
    if acao.tipo == "arrastar":
        assert acao.ate_x is not None and acao.ate_y is not None
        return [
            "xdotool",
            *mover,
            "mousedown",
            "1",
            "sleep",
            "0.15",
            "mousemove",
            "--sync",
            str(acao.ate_x),
            str(acao.ate_y),
            "sleep",
            "0.15",
            "mouseup",
            "1",
        ]
    if acao.tipo == "abrir":
        return ["sora-abrir", acao.programa or ""]
    raise ErroFerramenta(f"Ação não suportada: {acao.tipo}.")


def _png_de_saida(dados: bytes) -> Tela:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(dados)) as imagem:
            largura, altura = imagem.size
    except Exception as erro:
        raise ErroDocker("Não consegui capturar a tela do computador.") from erro
    return Tela(png=dados, largura=largura, altura=altura)


@dataclass(slots=True)
class ComputadorDocker:
    """Um computador virtual já ligado (o contêiner existe e está rodando)."""

    cliente: ClienteDocker
    nome: str
    alvo: Alvo = Alvo.VIRTUAL

    async def _exec(
        self, *argv: str, entrada: bytes | None = None, prazo: float = PRAZO_COMANDO_S
    ) -> subprocess.CompletedProcess[bytes]:
        argumentos = ["exec"]
        if entrada is not None:
            argumentos.append("-i")
        return await self.cliente.rodar(*argumentos, self.nome, *argv, entrada=entrada, prazo=prazo)

    async def observar(self) -> Observacao:
        captura, janelas = await asyncio.gather(
            self._exec("import", "-window", "root", "png:-"),
            self._exec("sora-janelas"),
        )
        if captura.returncode != 0 or not captura.stdout:
            raise ErroDocker("Não consegui capturar a tela do computador.")
        return Observacao(
            tela=_png_de_saida(captura.stdout),
            janelas=ler_janelas(janelas.stdout.decode(errors="replace")),
        )

    async def agir(self, acao: AcaoResolvida) -> None:
        if acao.janela is not None:
            await self._exec("wmctrl", "-i", "-a", acao.janela.id_nativo)
            await asyncio.sleep(0.2)
        prazo = PRAZO_COMANDO_S + (len(acao.acao.texto or "") * 0.03)
        resultado = await self._exec(*comando_xdotool(acao), prazo=prazo)
        if resultado.returncode != 0:
            raise ErroFerramenta(f"A ação {acao.acao.tipo} falhou no computador.")

    async def _dentro_da_area(self, relativo: str, *, deve_existir: bool) -> str:
        """Resolve links simbólicos dentro do contêiner e confere que o alvo fica na área."""
        caminho = f"{AREA}/{relativo}" if relativo else AREA
        opcao = "-e" if deve_existir else "-m"
        resultado = await self._exec("readlink", opcao, "--", caminho)
        real = resultado.stdout.decode(errors="replace").strip()
        if resultado.returncode != 0 or not real:
            raise ErroFerramenta("Esse arquivo não existe na sua área.")
        if real != AREA and not real.startswith(AREA + "/"):
            raise ErroFerramenta("Esse caminho sai da sua área de arquivos.")
        return real

    async def listar_arquivos(self, pasta: str) -> list[ArquivoArea]:
        real = await self._dentro_da_area(caminho_relativo(pasta), deve_existir=True)
        resultado = await self._exec(
            "find", real, "-mindepth", "1", "-maxdepth", "3", "-printf", "%y\t%s\t%P\n"
        )
        if resultado.returncode != 0:
            raise ErroFerramenta("Não consegui listar essa pasta.")
        itens: list[ArquivoArea] = []
        base = real[len(AREA) :].lstrip("/")
        for linha in resultado.stdout.decode(errors="replace").splitlines():
            tipo, _, resto = linha.partition("\t")
            tamanho, _, caminho = resto.partition("\t")
            if not caminho:
                continue
            itens.append(
                ArquivoArea(
                    caminho=f"{base}/{caminho}" if base else caminho,
                    tipo="arquivo" if tipo == "f" else "pasta" if tipo == "d" else "outro",
                    tamanho=int(tamanho) if tamanho.isdigit() else 0,
                )
            )
            if len(itens) >= MAX_ARQUIVOS_LISTADOS:
                break
        return sorted(itens, key=lambda item: item.caminho)

    async def ler_arquivo(self, caminho: str, limite: int) -> bytes:
        relativo = caminho_relativo(caminho)
        if not relativo:
            raise ErroFerramenta("Informe o arquivo.")
        real = await self._dentro_da_area(relativo, deve_existir=True)
        if (await self._exec("test", "-f", real)).returncode != 0:
            raise ErroFerramenta("Isso não é um arquivo.")
        resultado = await self._exec("head", "-c", str(limite + 1), "--", real)
        if resultado.returncode != 0:
            raise ErroFerramenta("Não consegui ler esse arquivo.")
        return resultado.stdout

    async def escrever_arquivo(self, caminho: str, dados: bytes) -> None:
        relativo = caminho_relativo(caminho)
        if not relativo:
            raise ErroFerramenta("Informe o nome do arquivo.")
        if len(dados) > MAX_ESCRITA_BYTES:
            raise ErroFerramenta("Arquivo grande demais (máximo 1 MB por vez).")
        pasta = relativo.rsplit("/", 1)[0] if "/" in relativo else ""
        if pasta:
            pasta_real = await self._dentro_da_area(pasta, deve_existir=False)
            await self._exec("mkdir", "-p", "--", pasta_real)
            await self._dentro_da_area(pasta, deve_existir=True)
        real = await self._dentro_da_area(relativo, deve_existir=False)
        # o caminho vai como argumento ($1), nunca dentro do texto do shell
        resultado = await self._exec("sh", "-c", 'cat > "$1"', "sh", real, entrada=dados)
        if resultado.returncode != 0:
            raise ErroFerramenta("Não consegui gravar o arquivo (a área pode estar cheia).")


@dataclass(slots=True)
class GerenteComputadoresDocker:
    """Liga, reaproveita e desliga os computadores virtuais dos bots."""

    cliente: ClienteDocker
    imagem: str = "sora-computador:1"
    imagem_proxy: str = "sora-proxy-egresso:1"
    tela: str = "1280x800x24"
    _travas: dict[UUID, asyncio.Lock] = field(default_factory=dict)
    _trava_proxy: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def _inspecionar(self, nome: str) -> tuple[bool, str] | None:
        resultado = await self.cliente.rodar(
            "inspect",
            "--type",
            "container",
            "--format",
            '{{.State.Running}}|{{index .Config.Labels "sora.usuario"}}',
            nome,
        )
        if resultado.returncode != 0:
            return None
        rodando, _, usuario = resultado.stdout.decode().strip().partition("|")
        return rodando == "true", usuario

    async def _garantir_proxy(self) -> None:
        async with self._trava_proxy:
            estado = await self._inspecionar(NOME_PROXY)
            if estado is not None and estado[0]:
                return
            if estado is not None:
                await self.cliente.rodar("start", NOME_PROXY)
                estado = await self._inspecionar(NOME_PROXY)
                if estado is not None and estado[0]:
                    return
                await self.cliente.rodar("rm", "-f", NOME_PROXY)
            rede = await self.cliente.rodar("network", "inspect", REDE_SAIDA)
            if rede.returncode != 0:
                await self.cliente.rodar(
                    "network", "create", "--label", f"{ROTULO}.saida=1", REDE_SAIDA
                )
            criado = await self.cliente.rodar(
                "run",
                "--detach",
                "--name",
                NOME_PROXY,
                "--network",
                REDE_SAIDA,
                "--restart",
                "unless-stopped",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",
                "--memory",
                "128m",
                "--cpus",
                "0.5",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--label",
                f"{ROTULO}.proxy=1",
                self.imagem_proxy,
            )
            if criado.returncode != 0 and b"Conflict" not in criado.stderr:
                registro.warning("proxy do computador: %s", criado.stderr.decode(errors="replace"))
                raise ErroDocker(
                    "A saída de rede do computador virtual não subiu "
                    f"(imagem {self.imagem_proxy} construída?)."
                )

    async def _garantir_rede(self, nome: str) -> None:
        if (await self.cliente.rodar("network", "inspect", nome)).returncode != 0:
            criada = await self.cliente.rodar(
                "network", "create", "--internal", "--label", f"{ROTULO}=1", nome
            )
            if criada.returncode != 0 and b"already exists" not in criada.stderr:
                raise ErroDocker("Não consegui criar a rede do computador virtual.")
        ligado = await self.cliente.rodar(
            "network", "connect", "--alias", ALIAS_PROXY, nome, NOME_PROXY
        )
        if ligado.returncode != 0 and b"already exists" not in ligado.stderr:
            raise ErroDocker("Não consegui ligar a saída de rede ao computador virtual.")

    async def _esperar_pronto(self, nome: str) -> None:
        limite = time.monotonic() + PRAZO_PRONTO_S
        while time.monotonic() < limite:
            pronto = await self.cliente.rodar("exec", nome, "test", "-f", "/tmp/sora-pronto")
            if pronto.returncode == 0:
                return
            estado = await self._inspecionar(nome)
            if estado is None or not estado[0]:
                break
            await asyncio.sleep(0.5)
        logs = await self.cliente.rodar("logs", "--tail", "20", nome)
        registro.warning("computador %s não ficou pronto: %s", nome, logs.stderr[-800:])
        raise ErroDocker("O computador virtual não ligou. Tente de novo em instantes.")

    async def obter(self, usuario_id: UUID, agente_id: UUID) -> ComputadorDocker:
        nome = nome_do_computador(agente_id)
        trava = self._travas.setdefault(agente_id, asyncio.Lock())
        async with trava:
            estado = await self._inspecionar(nome)
            if estado is not None:
                rodando, dono = estado
                if dono != str(usuario_id):
                    raise ErroDocker("Este computador virtual pertence a outra conta.")
                if rodando:
                    return ComputadorDocker(self.cliente, nome)
                await self.cliente.rodar("rm", "-f", nome)
            await self._garantir_proxy()
            await self._garantir_rede(nome)
            criado = await self.cliente.rodar(
                *argumentos_do_container(
                    agente_id=agente_id, usuario_id=usuario_id, imagem=self.imagem, tela=self.tela
                ),
                prazo=120,
            )
            if criado.returncode != 0 and b"Conflict" not in criado.stderr:
                registro.warning("computador %s: %s", nome, criado.stderr.decode(errors="replace"))
                raise ErroDocker(
                    f"Não consegui ligar o computador virtual (imagem {self.imagem} construída?)."
                )
            await self._esperar_pronto(nome)
            return ComputadorDocker(self.cliente, nome)

    async def desligar(self, agente_id: UUID) -> bool:
        nome = nome_do_computador(agente_id)
        trava = self._travas.setdefault(agente_id, asyncio.Lock())
        async with trava:
            return await self._remover(nome)

    async def _remover(self, nome: str) -> bool:
        removido = await self.cliente.rodar("rm", "-f", nome)
        with contextlib.suppress(ErroFerramenta):
            await self.cliente.rodar("network", "disconnect", "-f", nome, NOME_PROXY)
            await self.cliente.rodar("network", "rm", nome)
        return removido.returncode == 0 and bool(removido.stdout.strip())

    async def ligados(self) -> dict[UUID, str]:
        """Agente → nome do contêiner, para todos os computadores virtuais deste host."""
        resultado = await self.cliente.rodar(
            "ps",
            "--all",
            "--filter",
            f"label={ROTULO}=1",
            "--format",
            '{{.Names}}|{{.Label "sora.agente"}}',
        )
        saida: dict[UUID, str] = {}
        for linha in resultado.stdout.decode(errors="replace").splitlines():
            nome, _, agente = linha.strip().partition("|")
            with contextlib.suppress(ValueError):
                if nome.startswith(PREFIXO) and nome != NOME_PROXY:
                    saida[UUID(agente)] = nome
        return saida

    async def desligar_ociosos(self, ultimo_uso: dict[UUID, float], ocioso_s: float) -> list[UUID]:
        """Desliga quem não foi usado há ``ocioso_s`` segundos (sem registro de uso = ocioso)."""
        agora = time.time()
        desligados: list[UUID] = []
        for agente_id, nome in (await self.ligados()).items():
            if agora - ultimo_uso.get(agente_id, 0.0) < ocioso_s:
                continue
            trava = self._travas.setdefault(agente_id, asyncio.Lock())
            if trava.locked():
                continue
            async with trava:
                await self._remover(nome)
            self._travas.pop(agente_id, None)
            desligados.append(agente_id)
        return desligados
