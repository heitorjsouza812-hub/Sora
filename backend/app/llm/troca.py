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

from app.llm.limite import ErroLimiteDoProvedor

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
    outra_chave: bool = False
    """O mesmo modelo continua com outra chave da mesma conexão (chaves extras, migração 0019)."""


CHAVE_DA_CONEXAO = "sora_chave_da_conexao"
"""Em ``chat.metadata``: 0 = chave principal da conexão; 1, 2… = chaves extras, na ordem."""


def marcar_chave(chat: Any, indice: int) -> None:
    """Diz ao aviso de troca qual chave da conexão este modelo usa (sem a chave, só a posição)."""
    chat.metadata = {**(getattr(chat, "metadata", None) or {}), CHAVE_DA_CONEXAO: indice}


def _chave_de(chat: Any) -> int:
    return int((getattr(chat, "metadata", None) or {}).get(CHAVE_DA_CONEXAO, 0))


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
        if isinstance(atual, ErroLimiteDoProvedor):
            return None  # o limite do plano não cedeu: outro modelo do mesmo plano falharia igual
        motivo = _classificar_um(atual)
        if motivo is not None:
            return motivo
        atual = atual.__cause__ or atual.__context__
    return None


def _limite_que_nao_cedeu(erro: BaseException) -> bool:
    atual: BaseException | None = erro
    for _ in range(_PROFUNDIDADE_MAXIMA_DA_CAUSA):
        if atual is None:
            return False
        if isinstance(atual, ErroLimiteDoProvedor):
            return True
        atual = atual.__cause__ or atual.__context__
    return False


def deve_trocar(erro: BaseException) -> bool:
    """``classificar_erro(erro) is not None``. É o predicado que o middleware usa."""
    return classificar_erro(erro) is not None


def deve_repetir_no_mesmo(erro: BaseException) -> bool:
    """Repete no mesmo modelo só o que costuma passar logo (429, 5xx). Prazo estourado vai direto
    para o próximo da lista: repetir um modelo pendurado dobrava a espera do usuário."""
    motivo = classificar_erro(erro)
    return motivo is not None and motivo is not MotivoTroca.PRAZO


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
                posicao = next((i for i, m in enumerate(modelos) if m is request.model), None)
                proximo = (
                    modelos[posicao + 1]
                    if posicao is not None and posicao + 1 < len(modelos)
                    else None
                )
                if motivo is None and proximo is not None and _limite_que_nao_cedeu(erro):
                    # O limite do plano não cedeu na espera: outra chave (ou a reserva) segue.
                    motivo = MotivoTroca.LIMITE_DE_TAXA
                if motivo is not None:
                    de, para = _nome_do_modelo(request.model), None
                    if proximo is not None:
                        para = _nome_do_modelo(proximo)
                    await ao_trocar(
                        EventoTroca(
                            de_modelo=de,
                            para_modelo=para,
                            motivo=motivo,
                            outra_chave=(
                                proximo is not None
                                and para == de
                                and _chave_de(proximo) != _chave_de(request.model)
                            ),
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
    ao_falhar: Callable[[Any, BaseException], Awaitable[None]] | None = None,
    ao_responder: Callable[[Any], Awaitable[None]] | None = None,
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
            retry_on=deve_repetir_no_mesmo,
            on_failure="error",
            initial_delay=espera_inicial_s,
        )
    )
    if ao_falhar is not None or ao_responder is not None:
        # Por dentro da nova tentativa: cada chamada de verdade conta na saúde do provedor dela.
        middleware.append(_criar_monitor_de_saude(ao_falhar, ao_responder))
    return middleware


def _criar_monitor_de_saude(
    ao_falhar: Callable[[Any, BaseException], Awaitable[None]] | None,
    ao_responder: Callable[[Any], Awaitable[None]] | None,
) -> Any:
    """Middleware que conta, por modelo chamado, as falhas e as respostas (``app/llm/saude.py``)."""
    from langchain.agents.middleware import AgentMiddleware
    from langgraph.errors import GraphBubbleUp

    class MonitorDeSaude(AgentMiddleware):  # type: ignore[type-arg]
        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            try:
                resposta = await handler(request)
            except GraphBubbleUp:
                raise
            except Exception as erro:
                if ao_falhar is not None:
                    await ao_falhar(request.model, erro)
                raise
            if ao_responder is not None:
                await ao_responder(request.model)
            return resposta

    return MonitorDeSaude()
