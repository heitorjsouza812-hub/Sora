"""Eventos SSE dos canais da empresa, no stream agregado do usuário (``GET /v1/eventos``).

Ficam fora da união ``EventoEquipe`` (que ``tests`` congelam em 13 tipos); o app os consome pelo
nome. ``publicar`` usa o mesmo envelope dos demais eventos do usuário.
"""

from __future__ import annotations

import logging
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import Field

from app.eventos.tipos import EventoBase

registro = logging.getLogger(__name__)


class ClienteAtualizado(EventoBase):
    """A ficha de um cliente ganhou ou perdeu fatos."""

    evento: ClassVar[Literal["cliente.atualizado"]] = "cliente.atualizado"
    contato_id: UUID
    canal: str
    novos_fatos: int = 0
    total_fatos: int = 0
    motivo: Literal["leitura", "edicao", "remocao", "apagado"] = "leitura"


class ConhecimentoAtualizado(EventoBase):
    """A base de conhecimento ou as sugestões de melhoria mudaram."""

    evento: ClassVar[Literal["conhecimento.atualizado"]] = "conhecimento.atualizado"
    motivo: Literal[
        "leitura", "edicao", "remocao", "sugestoes", "aplicacao", "desfeita", "aprovacao"
    ]
    itens_novos: int = 0
    itens_atualizados: int = 0
    sugestoes_pendentes: int = 0
    sugestao_id: UUID | None = None
    agente_id: UUID | None = None
    detalhes: dict[str, int] = Field(default_factory=dict)


async def publicar(redis, evento: EventoBase, usuario_id: UUID) -> None:
    """Publica sem nunca derrubar quem chamou (o dado já está no banco)."""
    from app.eventos.equipe import publicar_evento_equipe

    try:
        await publicar_evento_equipe(redis, evento, usuario_id)  # type: ignore[arg-type]
    except Exception:
        registro.warning("não consegui publicar %s", evento.evento, exc_info=True)
