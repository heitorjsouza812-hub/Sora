"""Roda um processo com teto de saída e de tempo (``docker run``/``docker exec`` do sandbox e do
computador virtual).

``subprocess.run(capture_output=True)`` guarda TODA a saída na memória do worker antes de qualquer
corte: um ``yes`` ou ``cat /dev/urandom | base64`` dentro do contêiner (que tem 512 MB, mas o pipe
chega no worker) gerava gigabytes e derrubava o worker de todo mundo. Aqui a leitura para no teto,
o processo é morto e o chamador recebe ``cortado=True``.

Síncrono de propósito (o loop "selector" do worker no Windows não cria subprocessos
assíncronos): chamar com ``asyncio.to_thread``.
"""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from typing import IO

BLOCO = 64 * 1024


@dataclass(frozen=True, slots=True)
class SaidaProcesso:
    codigo: int | None
    stdout: bytes
    stderr: bytes
    estourou_prazo: bool = False
    cortado: bool = False
    """A saída passou de ``limite_bytes``: o processo foi morto e só o começo ficou."""


def _ler_com_teto(
    fluxo: IO[bytes], destino: bytearray, limite: int, estourou: threading.Event
) -> None:
    """Lê até o fim, guardando no máximo ``limite`` bytes; ao passar, avisa e para de ler."""
    ler = getattr(fluxo, "read1", fluxo.read)
    try:
        while bloco := ler(BLOCO):
            falta = limite - len(destino)
            if len(bloco) > falta:
                destino.extend(bloco[: max(falta, 0)])
                estourou.set()
                return
            destino.extend(bloco)
    except (OSError, ValueError):  # pipe fechado porque o processo foi morto
        return


def _escrever(fluxo: IO[bytes], dados: bytes) -> None:
    try:
        fluxo.write(dados)
    except (BrokenPipeError, OSError, ValueError):
        pass
    finally:
        try:
            fluxo.close()
        except OSError:
            pass


def rodar_limitado(
    argv: list[str],
    *,
    prazo: float,
    limite_bytes: int,
    env: dict[str, str] | None = None,
    entrada: bytes | None = None,
) -> SaidaProcesso:
    """Roda ``argv`` e devolve a saída, nunca guardando mais que ``limite_bytes`` por fluxo.

    Passou do prazo ou do teto: mata o processo (quem chamou remove o contêiner, porque matar o
    cliente ``docker`` não mata o contêiner)."""
    processo = subprocess.Popen(
        argv,
        env=env,
        stdin=subprocess.PIPE if entrada is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert processo.stdout is not None and processo.stderr is not None
    saida, erro = bytearray(), bytearray()
    estourou = threading.Event()
    leitores = [
        threading.Thread(
            target=_ler_com_teto, args=(processo.stdout, saida, limite_bytes, estourou), daemon=True
        ),
        threading.Thread(
            target=_ler_com_teto, args=(processo.stderr, erro, limite_bytes, estourou), daemon=True
        ),
    ]
    if entrada is not None and processo.stdin is not None:
        leitores.append(
            threading.Thread(target=_escrever, args=(processo.stdin, entrada), daemon=True)
        )
    for leitor in leitores:
        leitor.start()

    estourou_prazo = False
    cortado = False
    try:
        # Espera o fim do processo, acordando cedo se a saída passar do teto.
        restante = prazo
        while True:
            passo = min(0.1, restante) if restante > 0 else 0
            try:
                processo.wait(timeout=passo)
                break
            except subprocess.TimeoutExpired:
                pass
            if estourou.is_set():
                cortado = True
                break
            restante -= passo
            if restante <= 0:
                estourou_prazo = True
                break
    finally:
        if processo.poll() is None:
            processo.kill()
            try:
                processo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        for leitor in leitores:
            leitor.join(timeout=5)
        for fluxo in (processo.stdout, processo.stderr):
            try:
                fluxo.close()
            except OSError:
                pass
    cortado = cortado or estourou.is_set()
    return SaidaProcesso(
        codigo=None if estourou_prazo else processo.returncode,
        stdout=bytes(saida),
        stderr=bytes(erro),
        estourou_prazo=estourou_prazo,
        cortado=cortado,
    )
