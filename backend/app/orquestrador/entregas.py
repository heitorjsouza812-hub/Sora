"""Entregas e versões (especificação §1, tabela ``entregas``; §2, rotas
``/entregas`` e ``/aprovar`` e evento ``entrega``; §3.2, Revisão).

Cada chamada a ``entregar`` vira uma linha em ``entregas`` com a versão da
cadeia. A Revisão compara ``versao`` com ``versao - 1``; Aprovar grava
``conversas.aprovada_versao``.

Toda leitura e escrita por conversa recebe ``usuario_id`` (obrigatório, só por nome) e filtra
por ``conversas.usuario_id``: conversa de outro usuário = "não encontrada" (API-10, IDOR).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.modelos.enumeracoes import TipoEntrega


@dataclass(frozen=True, slots=True)
class NovaEntrega:
    """Dados para gravar uma entrega."""

    usuario_id: UUID
    conversa_id: UUID
    cadeia_id: UUID
    etapa_id: UUID | None
    agente_id: UUID | None
    versao: int
    tipo: TipoEntrega
    titulo: str
    resumo: str
    conteudo: dict[str, Any]


async def registrar_entrega(entrega: NovaEntrega) -> UUID:
    """Grava a entrega e emite o evento ``entrega``."""
    raise NotImplementedError


async def versoes_da_conversa(conversa_id: UUID, *, usuario_id: UUID) -> list[int]:
    """Lista as versões que têm entregas, da mais nova para a mais antiga (só do dono)."""
    raise NotImplementedError


async def entregas_da_versao(
    conversa_id: UUID, versao: int | None = None, *, usuario_id: UUID
) -> list[dict[str, Any]]:
    """Entregas de uma versão (padrão: a mais nova), só se a conversa for do usuário."""
    raise NotImplementedError


async def aprovar_versao(conversa_id: UUID, versao: int, *, usuario_id: UUID) -> None:
    """Grava ``conversas.aprovada_versao`` (só do dono) e emite ``conversa.atualizada``."""
    raise NotImplementedError
