"""Ciclo de vida de uma cadeia no banco (especificação §6, "Regras de execução").

Criação da cadeia, troca de estado com evento, escolha das etapas que já
podem rodar (``depende_de``, até 3 em paralelo), contagem de rodadas e
passos, cancelamento e progresso da etapa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from app.modelos.enumeracoes import StatusCadeia, StatusEtapa

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

PARALELO_POR_CADEIA = 3
"""Etapas independentes rodando ao mesmo tempo numa cadeia (§6)."""


@dataclass(frozen=True, slots=True)
class LimitesCadeia:
    """Limites da cadeia; os valores vêm de ``config/politica.yaml`` (§5)."""

    rodadas: int = 3
    passos: int = 10
    tokens: int = 200_000
    especialistas: int = 5


@dataclass(frozen=True, slots=True)
class EtapaResumo:
    """O mínimo de uma etapa para decidir o avanço da cadeia."""

    etapa_id: UUID
    ordem: int
    depende_de: tuple[int, ...]
    status: StatusEtapa


async def criar_cadeia(
    sessao: AsyncSession,
    *,
    usuario_id: UUID,
    conversa_id: UUID,
    pedido_id: UUID,
    orcamento_tokens: int,
    versao: int = 1,
) -> UUID:
    """Cria a cadeia em ``planejando`` e marca a conversa como ``projeto``."""
    raise NotImplementedError


async def mudar_status_cadeia(sessao: AsyncSession, cadeia_id: UUID, para: StatusCadeia) -> None:
    """Troca o estado da cadeia (checando a transição) e emite ``cadeia.atualizada``."""
    raise NotImplementedError


async def pegar_etapa(sessao: AsyncSession, etapa_id: UUID) -> bool:
    """``UPDATE ... WHERE status = 'pendente' RETURNING id``: sem trabalho em dobro.

    Devolve ``False`` se outro worker já pegou a etapa.
    """
    raise NotImplementedError


async def mudar_status_etapa(
    sessao: AsyncSession,
    etapa_id: UUID,
    para: StatusEtapa,
    *,
    erro: str | None = None,
) -> None:
    """Troca o estado da etapa e emite ``etapa.atualizada``."""
    raise NotImplementedError


def etapas_prontas(
    etapas: list[EtapaResumo], paralelo: int = PARALELO_POR_CADEIA
) -> list[EtapaResumo]:
    """Etapas pendentes cujas dependências já terminaram, respeitando o limite de paralelo."""
    raise NotImplementedError


def todas_concluidas(etapas: list[EtapaResumo]) -> bool:
    """Todas as etapas de execução (sem o Verificador) terminaram."""
    raise NotImplementedError


def passou_dos_limites(rodada: int, passos: int, limites: LimitesCadeia) -> bool:
    """A cadeia bateu no máximo de rodadas ou de passos."""
    raise NotImplementedError


def progresso_da_etapa(chamadas_feitas: int, limite_chamadas: int, entregou: bool) -> int:
    """Progresso de 0 a 100: 10 ao começar, até 85 pelas ferramentas, 100 no ``entregar``.

    Nunca volta para trás (§6, "Progresso da etapa").
    """
    raise NotImplementedError


async def cancelar_cadeia(sessao: AsyncSession, cadeia_id: UUID) -> None:
    """Marca ``cancelada`` e grava ``cancelar:{cadeia_id}`` no Redis."""
    raise NotImplementedError
