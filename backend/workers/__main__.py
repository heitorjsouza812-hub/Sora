"""Sobe o worker ARQ em qualquer sistema: ``uv run python -m workers`` (a partir de ``backend/``).

No Windows o ARQ não sobe sozinho: o psycopg assíncrono precisa do loop de eventos "selector"
(o padrão do Windows é o "proactor") e ``signal.SIGUSR1``, que o ARQ usa ao fechar, não existe.
No Linux (Docker) ``arq workers.configuracao.WorkerSettings`` continua valendo.
"""

from __future__ import annotations

import asyncio
import signal
import sys


def preparar_windows() -> None:
    """Ajustes que o ARQ e o psycopg pedem no Windows; não faz nada nos outros sistemas."""
    if sys.platform != "win32":
        return
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if not hasattr(signal, "SIGUSR1"):
        signal.SIGUSR1 = signal.SIGTERM  # type: ignore[attr-defined]


def main() -> None:
    from app.core.observabilidade import configurar_log

    preparar_windows()
    # O ``run_worker`` não configura ``logging`` (só o CLI do ``arq`` faz): sem isto o worker não
    # escreve nada. ``forcar``: aqui somos o processo principal.
    configurar_log(forcar=True)
    from arq.worker import run_worker

    from workers.configuracao import WorkerSettings

    run_worker(WorkerSettings)


if __name__ == "__main__":
    main()
