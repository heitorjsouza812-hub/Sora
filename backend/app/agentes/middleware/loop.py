"""Detector de loop (especificação §6, "Detector de loop"; §6.1).

Se a saída do modelo repetir a mesma linha 3 vezes seguidas, a chamada é
interrompida e refeita uma vez.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

REPETICOES_PARA_LOOP = 3


class LoopDoModelo(Exception):
    """O modelo repetiu a mesma linha mesmo depois de uma nova tentativa."""


def tem_loop(texto: str, repeticoes: int = REPETICOES_PARA_LOOP) -> bool:
    """A mesma linha aparece ``repeticoes`` vezes seguidas."""
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    return any(
        len(set(linhas[indice : indice + repeticoes])) == 1
        for indice in range(max(0, len(linhas) - repeticoes + 1))
    )


def _texto_da_resposta(resposta: ModelResponse) -> str:
    partes: list[str] = []
    for mensagem in resposta.result:
        conteudo = getattr(mensagem, "content", "")
        if isinstance(conteudo, str):
            partes.append(conteudo)
    return "\n".join(partes)


class MiddlewareLoop(AgentMiddleware):
    """Refaz uma vez a chamada de modelo que entrou em loop."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Any:
        primeira = await handler(request)
        if not tem_loop(_texto_da_resposta(primeira)):
            return primeira
        segunda = await handler(request)
        if tem_loop(_texto_da_resposta(segunda)):
            raise LoopDoModelo("O modelo repetiu a mesma linha após uma nova tentativa.")
        return segunda
