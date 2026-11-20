"""Ferramenta ``executar_comando`` (especificação §4, fase 3): roda um comando num computador
isolado e descartável.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``docker-sandbox.ts``,
``sandbox-command-environment.ts``, ``shell-command-stream.ts`` e ``sandbox-faults.ts``.

Diferença de propósito: no Rakazo cada bot tem um computador persistente com desktop
gráfico; aqui cada comando sobe um contêiner novo e jogado fora no fim (``--rm``), sem rede
por padrão, sem os arquivos do usuário, com memória, CPU, processos e tempo limitados. Isso
cobre análise de dados e conversão de arquivos sem manter máquinas ligadas. A ferramenta passa
pelo revisor de ações (``app/revisor/politica.py``).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.computador.processo import SaidaProcesso, rodar_limitado
from app.core.redacao import redigir
from app.ferramentas.base import LIMITE_RESULTADO_CARACTERES, ErroFerramenta

PRAZO_PADRAO_SEGUNDOS = 60
PRAZO_MAXIMO_SEGUNDOS = 300
LIMITE_SAIDA_BYTES = 1024 * 1024
"""Teto de cada fluxo (saída e erros) lido do contêiner. O modelo só vê uns 6 mil caracteres
(``cortar``); o teto existe para a saída nunca encher a memória do worker."""
REDE_COM_INTERNET = "sora-sbx-internet"
"""Rede interna (sem rota para fora) do comando com internet: a única saída é o proxy de egresso,
que recusa IP privado e de metadados da nuvem depois do DNS (o mesmo do computador virtual)."""
MEMORIA = "512m"
CPUS = "1"
MAX_PROCESSOS = 128
TMP_TAMANHO = "256m"

DESCRICAO = (
    "Roda um comando de shell num computador isolado e descartável (Linux, Python 3.12). Não "
    "tem acesso aos arquivos do usuário e, por padrão, não tem internet. Use para cálculos, "
    "análise de dados e conversão de arquivos."
)


class ExecutarComando(BaseModel):
    """Roda um comando num computador isolado e descartável."""

    comando: str = Field(min_length=1, max_length=8_000)
    prazo_segundos: int = Field(default=PRAZO_PADRAO_SEGUNDOS, ge=1, le=PRAZO_MAXIMO_SEGUNDOS)
    com_internet: bool = Field(
        default=False, description="Só quando o comando precisa baixar algo."
    )


@dataclass(frozen=True, slots=True)
class ResultadoComando:
    codigo_saida: int | None
    saida: str
    erro: str
    estourou_prazo: bool = False
    cortado: bool = False

    def para_modelo(self) -> str:
        partes = [
            f"código de saída: {'prazo estourado' if self.estourou_prazo else self.codigo_saida}"
        ]
        if self.cortado:
            partes.append(
                f"a saída passou de {LIMITE_SAIDA_BYTES // 1024} KB: o comando foi interrompido "
                "e só o começo está abaixo (redirecione para um arquivo ou filtre com head/grep)"
            )
        if self.saida:
            partes.append(f"saída:\n{self.saida}")
        if self.erro:
            partes.append(f"erros:\n{self.erro}")
        return "\n\n".join(partes)


class ProvedorSandbox(Protocol):
    async def executar(self, args: ExecutarComando, segredos: list[str]) -> ResultadoComando: ...


def cortar(texto: str, limite: int = LIMITE_RESULTADO_CARACTERES // 2) -> str:
    if len(texto) <= limite:
        return texto
    metade = limite // 2
    return f"{texto[:metade]}\n[… {len(texto) - limite} caracteres cortados …]\n{texto[-metade:]}"


@dataclass(slots=True)
class SandboxDocker:
    imagem: str = "python:3.12-slim"
    docker: str = "docker"
    docker_host: str | None = None
    """Host Docker separado (``DOCKER_HOST``); ``None`` usa o Docker local (só desenvolvimento)."""
    imagem_proxy: str = "sora-proxy-egresso:1"
    """Proxy de egresso (``infra/proxy-egresso``) do comando com internet."""
    nome: str = field(default_factory=lambda: f"sora-sbx-{uuid4().hex[:12]}")
    rotulos: dict[str, str] = field(default_factory=lambda: {"sora.sandbox": "1"})

    def montar_argumentos(self, args: ExecutarComando) -> list[str]:
        """``docker run`` com tudo travado. O comando vai como um único argumento do ``sh -c``.

        Com internet, o contêiner fica numa rede interna cuja única saída é o proxy de egresso
        (``--network bridge`` alcançaria a rede do host e o 169.254.169.254 da nuvem)."""
        from app.computador.virtual import ALIAS_PROXY, PORTA_PROXY

        argv = [
            self.docker,
            "run",
            "--rm",
            "--name",
            self.nome,
            "-i",
            "--network",
            REDE_COM_INTERNET if args.com_internet else "none",
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
            f"/trabalho:rw,nosuid,nodev,size={TMP_TAMANHO}",
            "--workdir",
            "/trabalho",
            "--user",
            "65534:65534",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--env",
            "HOME=/trabalho",
        ]
        if args.com_internet:
            proxy = f"http://{ALIAS_PROXY}:{PORTA_PROXY}"
            for variavel in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                argv += ["--env", f"{variavel}={proxy}"]
        for chave, valor in self.rotulos.items():
            argv += ["--label", f"{chave}={valor}"]
        return [*argv, self.imagem, "sh", "-c", args.comando]

    def _ambiente(self) -> dict[str, str]:
        ambiente = dict(os.environ)
        if self.docker_host:
            ambiente["DOCKER_HOST"] = self.docker_host
        return ambiente

    def _remover(self) -> None:
        """Matar o cliente não mata o contêiner: remove à força pelo nome."""
        subprocess.run(
            [self.docker, "rm", "-f", self.nome],
            env=self._ambiente(),
            capture_output=True,
            check=False,
            timeout=30,
        )

    def _rodar(self, args: ExecutarComando) -> SaidaProcesso:
        # subprocess em thread: o loop "selector" do Windows (usado pelo worker) não cria
        # subprocessos assíncronos. A saída tem teto (``rodar_limitado``).
        resultado = rodar_limitado(
            self.montar_argumentos(args),
            env=self._ambiente(),
            prazo=args.prazo_segundos + 10,
            limite_bytes=LIMITE_SAIDA_BYTES,
        )
        if resultado.estourou_prazo or resultado.cortado:
            self._remover()
        return resultado

    async def _preparar_rede(self) -> None:
        """Rede interna + proxy de egresso para o comando com internet (idempotente)."""
        from app.computador.virtual import (
            ClienteDocker,
            garantir_proxy_de_saida,
            garantir_rede_interna,
        )

        cliente = ClienteDocker(docker=self.docker, docker_host=self.docker_host)
        await garantir_proxy_de_saida(cliente, self.imagem_proxy)
        await garantir_rede_interna(cliente, REDE_COM_INTERNET, rotulo="sora.sandbox=1")

    async def executar(self, args: ExecutarComando, segredos: list[str]) -> ResultadoComando:
        if shutil.which(self.docker) is None:
            raise ErroFerramenta("O computador isolado não está disponível neste servidor.")
        if args.com_internet:
            await self._preparar_rede()
        resultado = await asyncio.to_thread(self._rodar, args)
        if resultado.estourou_prazo:
            return ResultadoComando(None, "", "", estourou_prazo=True)
        return ResultadoComando(
            resultado.codigo,
            cortar(redigir(resultado.stdout.decode(errors="replace"), segredos)),
            cortar(redigir(resultado.stderr.decode(errors="replace"), segredos)),
            cortado=resultado.cortado,
        )


@dataclass(slots=True)
class SandboxFalso:
    """Para testes: devolve respostas prontas por comando."""

    respostas: dict[str, ResultadoComando] = field(default_factory=dict)
    chamadas: list[str] = field(default_factory=list)

    async def executar(self, args: ExecutarComando, segredos: list[str]) -> ResultadoComando:
        self.chamadas.append(args.comando)
        return self.respostas.get(args.comando, ResultadoComando(0, "", ""))


def obter_sandbox(
    provedor: str,
    imagem: str,
    docker_host: str | None = None,
    imagem_proxy: str = "sora-proxy-egresso:1",
) -> ProvedorSandbox:
    if provedor == "docker":
        return SandboxDocker(
            imagem=imagem, docker_host=docker_host or None, imagem_proxy=imagem_proxy
        )
    raise ErroFerramenta("O computador isolado está desligado (SANDBOX_PROVEDOR=nenhum).")
