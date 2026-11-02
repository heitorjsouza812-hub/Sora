"""Worker ARQ que trava dentro da etapa, para provar a morte de um processo de verdade.

Roda como processo separado (``python worker_lento.py``): imprime ``TRAVADO-NA-ETAPA`` quando o
agente entra na etapa e dorme. O teste mata o processo nessa hora.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from workers.__main__ import preparar_windows

preparar_windows()

import app.agentes as agentes  # noqa: E402


async def travar(*args: object, **kwargs: object) -> None:
    print("TRAVADO-NA-ETAPA", flush=True)
    await asyncio.sleep(3600)


agentes.montar_e_rodar_agente = travar  # type: ignore[assignment]

from arq.connections import RedisSettings  # noqa: E402
from arq.worker import create_worker  # noqa: E402

from workers.configuracao import WorkerSettings  # noqa: E402


async def principal() -> None:
    worker = create_worker(
        WorkerSettings,
        redis_settings=RedisSettings.from_dsn(os.environ["REDIS_URL"]),
        handle_signals=False,
        poll_delay=0.1,
    )
    await worker.async_run()


asyncio.run(principal())
