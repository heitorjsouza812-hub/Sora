"""Troca de provedor em falha e pausa de provedor.

Especificação: §5 regra "Falhas" (429, 5xx ou prazo estourado passam para o próximo modelo da
lista; 3 falhas seguidas pausam o provedor por 5 minutos), §6 "Falha de provedor" e §6.1 (peças
de engenharia → ``ModelRetryMiddleware`` + ``ModelFallbackMiddleware``).

Os limites (3 falhas, 5 minutos) vêm de ``politica.yaml``; este módulo recebe os valores.
O estado de saúde fica nas colunas ``falhas_seguidas`` e ``pausado_ate`` de ``provedores``; o
acesso ao banco entra por ``ArmazemSaude`` para o módulo ser testável sem banco.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from pydantic import BaseModel

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


class MotivoTroca(StrEnum):
    LIMITE_DE_TAXA = "limite_de_taxa"  # 429
    ERRO_DO_SERVIDOR = "erro_do_servidor"  # 5xx
    PRAZO = "prazo"  # timeout


class EventoTroca(BaseModel):
    """Vira um evento na linha do tempo quando o worker troca de modelo."""

    de_modelo: str
    para_modelo: str | None
    motivo: MotivoTroca


class EstadoSaude(BaseModel):
    provedor_id: UUID
    falhas_seguidas: int = 0
    pausado_ate: datetime | None = None


class ArmazemSaude(Protocol):
    """Leitura e gravação do estado de saúde de um provedor (implementado sobre ``provedores``)."""

    async def obter(self, provedor_id: UUID) -> EstadoSaude: ...

    async def salvar(self, estado: EstadoSaude) -> None: ...


def classificar_erro(erro: BaseException) -> MotivoTroca | None:
    """Diz se o erro justifica trocar de modelo (429, 5xx, prazo). ``None`` = não troca."""
    raise NotImplementedError


def deve_trocar(erro: BaseException) -> bool:
    """``classificar_erro(erro) is not None``. É o predicado que o middleware usa."""
    raise NotImplementedError


async def registrar_falha(
    armazem: ArmazemSaude,
    provedor_id: UUID,
    *,
    falhas_para_pausar: int,
    pausa_minutos: int,
) -> EstadoSaude:
    """Soma uma falha e, ao chegar no limite, pausa o provedor."""
    raise NotImplementedError


async def registrar_sucesso(armazem: ArmazemSaude, provedor_id: UUID) -> EstadoSaude:
    """Zera as falhas seguidas do provedor."""
    raise NotImplementedError


def montar_middleware_de_troca(
    modelos: Sequence[BaseChatModel],
    *,
    ao_trocar: Callable[[EventoTroca], Awaitable[None]] | None = None,
) -> list[Any]:
    """Fábrica ÚNICA do middleware de troca de provedor: ``ModelRetryMiddleware`` +
    ``ModelFallbackMiddleware`` com os modelos na ordem do seletor (o primeiro é o principal).
    ``ao_trocar`` é chamado para gerar o evento da troca.

    ``app/agentes/middleware/troca_provedor.py`` (Trama) só reexporta esta função e
    ``deve_trocar``; a lógica fica aqui.
    """
    raise NotImplementedError
