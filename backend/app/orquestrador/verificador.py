"""Verificador da cadeia (especificação §6, job ``verificar_cadeia``; prompt em
``prompts/verificador.v1.md``; ferramenta ``veredito`` em §4).

Roda no N2, sempre com um modelo diferente do que executou as etapas.
Regra de reprovação: as etapas apontadas ganham uma nova tentativa um nível
acima, uma única vez; na segunda reprovação a cadeia vai para ``falhou``.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.ferramentas.veredito import Veredito


@dataclass(frozen=True, slots=True)
class DecisaoVerificacao:
    """O que fazer depois do veredito."""

    concluir: bool
    refazer_etapas: tuple[UUID, ...] = ()
    falhar: bool = False
    motivo: str = ""


async def verificar(cadeia_id: UUID) -> Veredito:
    """Roda o agente Verificador sobre os resultados da cadeia."""
    raise NotImplementedError


def decidir(veredito: Veredito, *, rodada: int, max_rodadas: int) -> DecisaoVerificacao:
    """Aplica a regra de reprovação ao veredito."""
    raise NotImplementedError


def subir_nivel(nivel: str) -> str:
    """N1 → N2 → N3 (N3 fica em N3), para a nova tentativa de uma etapa reprovada."""
    raise NotImplementedError
