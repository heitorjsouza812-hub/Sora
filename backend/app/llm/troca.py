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
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

import httpx
from pydantic import BaseModel

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

_PROFUNDIDADE_MAXIMA_DA_CAUSA = 5


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


def _status_http(erro: BaseException) -> int | None:
    status = getattr(erro, "status_code", None)
    if status is None:
        status = getattr(getattr(erro, "response", None), "status_code", None)
    return status if isinstance(status, int) else None


def _classificar_um(erro: BaseException) -> MotivoTroca | None:
    from litellm import exceptions as le

    if isinstance(erro, TimeoutError | httpx.TimeoutException | le.Timeout):
        return MotivoTroca.PRAZO
    status = _status_http(erro)
    if status == 429:
        return MotivoTroca.LIMITE_DE_TAXA
    if status is not None and 500 <= status < 600:
        return MotivoTroca.ERRO_DO_SERVIDOR
    if isinstance(erro, le.RateLimitError):
        return MotivoTroca.LIMITE_DE_TAXA
    if isinstance(
        erro,
        le.InternalServerError
        | le.ServiceUnavailableError
        | le.BadGatewayError
        | le.APIConnectionError,
    ):
        return MotivoTroca.ERRO_DO_SERVIDOR
    return None


def classificar_erro(erro: BaseException) -> MotivoTroca | None:
    """Diz se o erro justifica trocar de modelo (429, 5xx, prazo). ``None`` = não troca.

    Chave inválida (401/403), pedido malformado (400) e contexto estourado não trocam: o próximo
    modelo falharia do mesmo jeito ou o problema é do usuário. Segue a cadeia de causas.
    """
    atual: BaseException | None = erro
    for _ in range(_PROFUNDIDADE_MAXIMA_DA_CAUSA):
        if atual is None:
            break
        motivo = _classificar_um(atual)
        if motivo is not None:
            return motivo
        atual = atual.__cause__ or atual.__context__
    return None


def deve_trocar(erro: BaseException) -> bool:
    """``classificar_erro(erro) is not None``. É o predicado que o middleware usa."""
    return classificar_erro(erro) is not None


async def registrar_falha(
    armazem: ArmazemSaude,
    provedor_id: UUID,
    *,
    falhas_para_pausar: int,
    pausa_minutos: int,
    agora: datetime | None = None,
) -> EstadoSaude:
    """Soma uma falha e, ao chegar no limite, pausa o provedor por ``pausa_minutos``."""
    agora = agora or datetime.now(UTC)
    estado = await armazem.obter(provedor_id)
    estado = estado.model_copy(update={"falhas_seguidas": estado.falhas_seguidas + 1})
    if estado.falhas_seguidas >= falhas_para_pausar:
        estado = estado.model_copy(update={"pausado_ate": agora + timedelta(minutes=pausa_minutos)})
    await armazem.salvar(estado)
    return estado


async def registrar_sucesso(armazem: ArmazemSaude, provedor_id: UUID) -> EstadoSaude:
    """Zera as falhas seguidas e a pausa do provedor."""
    estado = await armazem.obter(provedor_id)
    estado = estado.model_copy(update={"falhas_seguidas": 0, "pausado_ate": None})
    await armazem.salvar(estado)
    return estado


def _nome_do_modelo(modelo: Any) -> str:
    return str(getattr(modelo, "model_name", None) or getattr(modelo, "model", None) or modelo)


def _criar_notificador(
    modelos: Sequence[BaseChatModel],
    ao_trocar: Callable[[EventoTroca], Awaitable[None]],
) -> Any:
    """Middleware que avisa ``ao_trocar`` cada vez que um modelo falha de um jeito trocável."""
    from langchain.agents.middleware import AgentMiddleware
    from langgraph.errors import GraphBubbleUp

    class NotificadorDeTroca(AgentMiddleware):  # type: ignore[type-arg]
        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            try:
                return await handler(request)
            except GraphBubbleUp:
                raise
            except Exception as erro:
                motivo = classificar_erro(erro)
                if motivo is not None:
                    posicao = next((i for i, m in enumerate(modelos) if m is request.model), None)
                    proximo = (
                        modelos[posicao + 1]
                        if posicao is not None and posicao + 1 < len(modelos)
                        else None
                    )
                    await ao_trocar(
                        EventoTroca(
                            de_modelo=_nome_do_modelo(request.model),
                            para_modelo=None if proximo is None else _nome_do_modelo(proximo),
                            motivo=motivo,
                        )
                    )
                raise

    return NotificadorDeTroca()


def montar_middleware_de_troca(
    modelos: Sequence[BaseChatModel],
    *,
    ao_trocar: Callable[[EventoTroca], Awaitable[None]] | None = None,
    tentativas_no_mesmo_modelo: int = 1,
    espera_inicial_s: float = 0.5,
) -> list[Any]:
    """Fábrica ÚNICA do middleware de troca de provedor: ``ModelRetryMiddleware`` +
    ``ModelFallbackMiddleware`` com os modelos na ordem do seletor (o primeiro é o principal).
    ``ao_trocar`` é chamado para gerar o evento da troca.

    ``app/agentes/middleware/troca_provedor.py`` (Trama) só reexporta esta função e
    ``deve_trocar``; a lógica fica aqui.

    O primeiro modelo da lista é o que vai em ``create_agent(model=...)``; os demais viram
    reservas. Ordem do middleware (de fora para dentro): reservas → aviso de troca → nova
    tentativa no mesmo modelo. Só erros que ``deve_trocar`` aceita são repetidos ou trocados.
    """
    if not modelos:
        raise ValueError("A lista de modelos do seletor está vazia.")

    from langchain.agents.middleware import ModelFallbackMiddleware, ModelRetryMiddleware

    middleware: list[Any] = []
    if len(modelos) > 1:
        middleware.append(ModelFallbackMiddleware(*modelos[1:]))
    if ao_trocar is not None:
        middleware.append(_criar_notificador(modelos, ao_trocar))
    middleware.append(
        ModelRetryMiddleware(
            max_retries=tentativas_no_mesmo_modelo,
            retry_on=deve_trocar,
            on_failure="error",
            initial_delay=espera_inicial_s,
        )
    )
    return middleware
