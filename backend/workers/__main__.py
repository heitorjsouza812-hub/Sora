"""Sobe o worker ARQ em qualquer sistema: ``uv run python -m workers`` (a partir de ``backend/``).

No Windows o ARQ não sobe sozinho: o psycopg assíncrono precisa do loop de eventos "selector"
(o padrão do Windows é o "proactor") e ``signal.SIGUSR1``, que o ARQ usa ao fechar, não existe.
No Linux (Docker) ``arq workers.configuracao.WorkerSettings`` continua valendo.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys


def preparar_windows() -> None:
    """Ajustes que o ARQ e o psycopg pedem no Windows; não faz nada nos outros sistemas."""
    if sys.platform != "win32":
        return
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if not hasattr(signal, "SIGUSR1"):
        signal.SIGUSR1 = signal.SIGTERM  # type: ignore[attr-defined]


FORMATO_LOG = "%(levelname)s:     %(name)s: %(message)s"
"""Mesmo desenho do log da API (uvicorn): ``INFO:     mensagem``, com o nome do logger."""


def configurar_log(nivel: int = logging.INFO) -> None:
    """O ``run_worker`` não configura ``logging`` (só o CLI do ``arq`` faz). Sem isto o worker
    não escreve nada. A saída vai em UTF-8: os ``→``/``←`` do ARQ quebram em cp1252 no Windows."""
    for fluxo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(fluxo, "reconfigure", None)
        if reconfigurar is not None:
            reconfigurar(encoding="utf-8", errors="replace")
    logging.basicConfig(level=nivel, format=FORMATO_LOG, stream=sys.stderr, force=True)


def main() -> None:
    preparar_windows()
    configurar_log()
    from arq.worker import run_worker

    from workers.configuracao import WorkerSettings

    run_worker(WorkerSettings)


if __name__ == "__main__":
    main()
