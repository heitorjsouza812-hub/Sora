"""Logs e Sentry da API e do worker; especificação §8.3.

Antes, ``SENTRY_DSN`` existia na configuração mas nada chamava ``sentry_sdk.init``, e o log só era
configurado em ``workers/__main__.py`` (o atalho de desenvolvimento): em produção o worker sobe
pelo CLI do ``arq``, que só configura o logger ``arq``, e os ``registro.info`` do app sumiam.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Configuracao

FORMATO_LOG = "%(levelname)s:     %(name)s: %(message)s"
"""Mesmo desenho do log da API (uvicorn): ``INFO:     mensagem``, com o nome do logger."""

registro = logging.getLogger(__name__)


def configurar_log(nivel: int | str | None = None, *, forcar: bool = False) -> None:
    """Log do app em stderr, em UTF-8 (os ``→``/``←`` do ARQ quebram em cp1252 no Windows).

    ``LOG_NIVEL`` (``DEBUG``, ``INFO``…) muda o nível; o padrão é ``INFO``. Sem ``forcar``, não
    mexe num log que alguém já configurou (pytest, uvicorn com ``--log-config``)."""
    nivel = nivel or os.environ.get("LOG_NIVEL", "INFO").upper()
    for fluxo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(fluxo, "reconfigure", None)
        if reconfigurar is not None:
            try:
                reconfigurar(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # fluxo já em uso ou trocado (pytest)
                pass
    raiz = logging.getLogger()
    if raiz.handlers and not forcar:
        return
    logging.basicConfig(level=nivel, format=FORMATO_LOG, stream=sys.stderr, force=forcar)


def iniciar_sentry(config: Configuracao, componente: str) -> bool:
    """Liga o Sentry quando há ``SENTRY_DSN``. Devolve se ligou.

    Sem dados pessoais: sem cabeçalhos/cookies (``send_default_pii=False``), sem corpo das
    requisições (senhas e chaves de API passam por elas) e sem variáveis locais nas pilhas."""
    dsn = (config.sentry_dsn or "").strip()
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=config.ambiente,
        server_name=componente,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sample_rate=0.0,
    )
    sentry_sdk.set_tag("componente", componente)
    registro.info("Sentry ligado (%s)", componente)
    return True
