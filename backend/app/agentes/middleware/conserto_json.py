"""Conserto de JSON (especificação §6.1 e §4, "Argumentos inválidos").

``ToolErrorMiddleware``: o erro de validação volta para o modelo tentar de novo
uma vez. Na saída estruturada, ``handle_errors`` do ``ToolStrategy``.

Engrenagem: uma exceção inesperada dentro de uma ferramenta (rede, navegador, banco) também
volta ao modelo como erro curto, sem detalhe interno, em vez de derrubar o turno inteiro (antes o
usuário recebia "o modelo de IA não respondeu", que não era verdade). Ficam de fora o que precisa
mesmo parar o turno (cancelamento, limites) e as ferramentas que mandam mensagem ao usuário: se
``falar`` falhou depois de gravar, repetir duplicaria a mensagem.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware

registro = logging.getLogger(__name__)

FERRAMENTAS_SEM_REPETICAO = frozenset({"falar", "canal_resultado"})
"""Mandam mensagem ao usuário: falha inesperada nelas continua derrubando o turno."""


def _deve_parar_o_turno(erro: Exception) -> bool:
    from app.agentes.middleware.cancelamento import CadeiaCancelada
    from app.agentes.middleware.limites import estourou_limite_de_passos
    from app.agentes.middleware.loop import LoopDoModelo
    from app.llm.limite import ErroLimiteDoProvedor

    return isinstance(
        erro, CadeiaCancelada | LoopDoModelo | ErroLimiteDoProvedor
    ) or estourou_limite_de_passos(erro)


def middleware_de_conserto() -> AgentMiddleware:
    """``ToolErrorMiddleware`` devolvendo o erro de validação ao modelo."""
    from langchain.agents.middleware import ToolErrorMiddleware

    def ao_erro(erro: Exception, request: Any) -> str | None:
        if isinstance(erro, (ValidationError, TypeError, ValueError)):
            return mensagem_de_erro_de_validacao(erro)
        nome = str((getattr(request, "tool_call", None) or {}).get("name", ""))
        if _deve_parar_o_turno(erro) or nome in FERRAMENTAS_SEM_REPETICAO:
            return None
        registro.warning("a ferramenta %s falhou", nome, exc_info=erro)
        return mensagem_de_falha_inesperada(nome, erro)

    return ToolErrorMiddleware(on_error=ao_erro)


def mensagem_de_falha_inesperada(nome: str, erro: Exception) -> str:
    """Só o tipo do erro: a mensagem pode trazer detalhe interno (endereço, consulta, caminho)."""
    return (
        f"Erro: a ferramenta {nome} falhou ({type(erro).__name__}). Tente de novo uma vez; se "
        "falhar de novo, siga sem ela e diga ao usuário o que não deu para fazer."
    )


def mensagem_de_erro_de_validacao(erro: Exception) -> str:
    """Texto curto do erro de validação que o modelo recebe."""
    if isinstance(erro, ValidationError):
        detalhes = "; ".join(
            f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in erro.errors()[:5]
        )
    else:
        detalhes = str(erro)
    return f"Argumentos inválidos: {detalhes[:800]}. Corrija e tente uma vez de novo."
