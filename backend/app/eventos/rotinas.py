"""Evento das rotinas. Fora da união ``Evento`` (como ``eventos/equipe.py``): entra nela junto
com o exemplo em ``tests/contrato`` quando o app tiver a tela."""

from __future__ import annotations

from typing import ClassVar, Literal
from uuid import UUID

from app.eventos.tipos import EventoBase


class RotinaExecutada(EventoBase):
    evento: ClassVar[Literal["rotina.executada"]] = "rotina.executada"
    rotina_id: UUID
    execucao_id: UUID
    status: Literal["enviada", "silenciosa", "falhou"]
    mensagem_id: UUID | None = None
