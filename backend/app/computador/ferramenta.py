"""Função da ferramenta ``executar_comando`` (o esquema está em ``__init__.py``).

Só liga com ``SANDBOX_PROVEDOR=docker``; em produção, só com ``SANDBOX_DOCKER_HOST`` (host
separado). A política (``revisor``) é aplicada por quem executa a ferramenta; numa rotina sem
supervisão ela nem aparece.
"""

from __future__ import annotations

from app.computador import ExecutarComando, obter_sandbox
from app.core.config import obter_configuracao
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta


async def executar_comando(args: ExecutarComando, contexto: ContextoFerramenta) -> str:
    config = obter_configuracao()
    if contexto.sem_supervisao:
        raise ErroFerramenta("O computador isolado não roda em rotinas sem supervisão.")
    if not config.sandbox_ativo:
        raise ErroFerramenta("O computador isolado está desligado neste servidor.")
    sandbox = obter_sandbox(config.sandbox_provedor, config.sandbox_imagem, config.sandbox_docker_host)
    resultado = await sandbox.executar(args, [])
    return resultado.para_modelo()
