"""Limite de passos da etapa (especificação §6.1).

``ModelCallLimitMiddleware`` e ``ToolCallLimitMiddleware`` do LangChain, com ``run_limit``.
Uma tarefa de navegador (abrir, observar, procurar, clicar, observar, capturar, entregar e as
esperas) pede bem mais chamadas que uma tarefa de texto: ``limites_do_agente`` dá mais folga
quando o agente tem ferramentas do navegador, e o limite continua valendo como proteção.

Uma chamada antes do fim o agente recebe o aviso para entregar o que tem
(``MiddlewareAvisoDeUltimoPasso``); se mesmo assim estourar, a mensagem ao usuário diz a verdade
(``MENSAGEM_LIMITE_DE_PASSOS``), não que o modelo "não respondeu".
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage

if TYPE_CHECKING:
    from app.agentes.montagem import ContextoAgente

LIMITE_PADRAO = (10, 10)
"""(chamadas do modelo, chamadas de ferramenta) por execução, sem navegador."""
LIMITE_COM_NAVEGADOR = (25, 40)
"""O mesmo, quando o agente tem ferramentas do navegador."""

MENSAGEM_LIMITE_DE_PASSOS = (
    "A etapa usou o máximo de passos permitido sem terminar. "
    "Peça de novo com uma tarefa mais simples."
)

AVISO_ULTIMO_PASSO = (
    "Aviso do sistema: esta é a sua ÚLTIMA chamada antes do limite de passos. Entregue agora, "
    "com a ferramenta de entrega, o que você já reuniu (diga o que ficou faltando). Não abra "
    "nem observe mais nada."
)


def _inteiro_do_ambiente(nome: str, padrao: int) -> int:
    try:
        valor = int(os.environ.get(nome, ""))
    except ValueError:
        return padrao
    return valor if valor >= 1 else padrao


def limites_do_agente(contexto: ContextoAgente) -> tuple[int, int]:
    """(modelo, ferramenta). Configurável por ``SORA_MAX_CHAMADAS_MODELO`` e
    ``SORA_MAX_CHAMADAS_MODELO_NAVEGADOR`` (a de ferramenta acompanha em 1,6x)."""
    from app.agentes.montagem import FERRAMENTAS_NAVEGADOR, nomes_das_ferramentas

    if any(nome in FERRAMENTAS_NAVEGADOR for nome in nomes_das_ferramentas(contexto)):
        modelo = _inteiro_do_ambiente("SORA_MAX_CHAMADAS_MODELO_NAVEGADOR", LIMITE_COM_NAVEGADOR[0])
        return modelo, max(modelo, round(modelo * 1.6))
    modelo = _inteiro_do_ambiente("SORA_MAX_CHAMADAS_MODELO", LIMITE_PADRAO[0])
    return modelo, max(modelo, LIMITE_PADRAO[1])


def estourou_limite_de_passos(erro: BaseException) -> bool:
    from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
    from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError

    atual: BaseException | None = erro
    for _ in range(5):
        if atual is None:
            return False
        if isinstance(atual, ModelCallLimitExceededError | ToolCallLimitExceededError):
            return True
        atual = atual.__cause__ or atual.__context__
    return False


class MiddlewareAvisoDeUltimoPasso(AgentMiddleware):
    """Na penúltima chamada do modelo, avisa que a próxima é a última."""

    def __init__(self, limite_modelo: int) -> None:
        self.limite_modelo = limite_modelo
        self._avisou = False

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        feitas = state.get("run_model_call_count") if isinstance(state, dict) else None
        if self._avisou or not isinstance(feitas, int) or feitas != self.limite_modelo - 1:
            return None
        self._avisou = True
        return {"messages": [SystemMessage(content=AVISO_ULTIMO_PASSO)]}


def middleware_de_limites(
    max_chamadas_modelo: int, max_chamadas_ferramenta: int
) -> list[AgentMiddleware]:
    """Os dois limites configurados para uma execução da etapa, mais o aviso do último passo."""
    if max_chamadas_modelo < 1 or max_chamadas_ferramenta < 1:
        raise ValueError("Os limites de chamadas precisam ser positivos.")
    from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

    return [
        ModelCallLimitMiddleware(run_limit=max_chamadas_modelo, exit_behavior="error"),
        ToolCallLimitMiddleware(run_limit=max_chamadas_ferramenta, exit_behavior="error"),
        MiddlewareAvisoDeUltimoPasso(max_chamadas_modelo),
    ]
