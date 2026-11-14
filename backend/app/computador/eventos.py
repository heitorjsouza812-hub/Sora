"""Evento SSE da tela do computador do bot (painel Trabalho mostra a tela ao vivo).

Vai pelo stream do usuário (``GET /v1/eventos``), como as peças da equipe
(``app/eventos/equipe.py``). Fica fora da união ``Evento`` de ``app/eventos/tipos.py`` até o app
consumir e o contrato JSON ser congelado em ``tests/contrato``.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import Field

from app.eventos.tipos import EventoBase

MAX_MINIATURA_BYTES = 64 * 1024
"""Miniatura maior que isso não vai no evento; o app busca ``GET …/computador/captura``."""


class TelaComputadorEvento(EventoBase):
    evento: ClassVar[Literal["computador.tela"]] = "computador.tela"
    agente_id: UUID
    alvo: Literal["virtual", "pc_usuario"]
    ligado: bool
    geracao: int = 0
    largura: int = 0
    altura: int = 0
    miniatura: str | None = Field(
        default=None, description="data:image/jpeg;base64,… (até 480 px de largura)"
    )
    janela_ativa: str | None = None
    acao: str | None = Field(default=None, description="Rótulo curto; nunca o texto digitado.")
    mudou: bool | None = None
    em: datetime
