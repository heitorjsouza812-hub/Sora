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
import shutil
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field

from app.core.redacao import redigir
from app.ferramentas.base import LIMITE_RESULTADO_CARACTERES, ErroFerramenta

PRAZO_PADRAO_SEGUNDOS = 60
PRAZO_MAXIMO_SEGUNDOS = 300
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

    def para_modelo(self) -> str:
        partes = [
            f"código de saída: {'prazo estourado' if self.estourou_prazo else self.codigo_saida}"
        ]
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
    rotulos: dict[str, str] = field(default_factory=lambda: {"sora.sandbox": "1"})

    def montar_argumentos(self, args: ExecutarComando) -> list[str]:
        """``docker run`` com tudo travado. O comando vai como um único argumento do ``sh -c``."""
        argv = [
            self.docker,
            "run",
            "--rm",
            "-i",
            "--network",
            "bridge" if args.com_internet else "none",
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
        for chave, valor in self.rotulos.items():
            argv += ["--label", f"{chave}={valor}"]
        return [*argv, self.imagem, "sh", "-c", args.comando]

    async def executar(self, args: ExecutarComando, segredos: list[str]) -> ResultadoComando:
        if shutil.which(self.docker) is None:
            raise ErroFerramenta("O computador isolado não está disponível neste servidor.")
        processo = await asyncio.create_subprocess_exec(
            *self.montar_argumentos(args),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            saida, erro = await asyncio.wait_for(processo.communicate(), args.prazo_segundos + 10)
        except TimeoutError:
            processo.kill()
            await processo.wait()
            return ResultadoComando(None, "", "", estourou_prazo=True)
        return ResultadoComando(
            processo.returncode,
            cortar(redigir(saida.decode(errors="replace"), segredos)),
            cortar(redigir(erro.decode(errors="replace"), segredos)),
        )


@dataclass(slots=True)
class SandboxFalso:
    """Para testes: devolve respostas prontas por comando."""

    respostas: dict[str, ResultadoComando] = field(default_factory=dict)
    chamadas: list[str] = field(default_factory=list)

    async def executar(self, args: ExecutarComando, segredos: list[str]) -> ResultadoComando:
        self.chamadas.append(args.comando)
        return self.respostas.get(args.comando, ResultadoComando(0, "", ""))


def obter_sandbox(provedor: str, imagem: str) -> ProvedorSandbox:
    if provedor == "docker":
        return SandboxDocker(imagem=imagem)
    raise ErroFerramenta("O computador isolado está desligado (SANDBOX_PROVEDOR=nenhum).")
