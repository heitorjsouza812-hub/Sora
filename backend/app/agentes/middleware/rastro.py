"""Rastro de uma execução do agente (2026-11-22): seguir um pedido de ponta a ponta.

Desligado por padrão. Com ``SORA_RASTRO=1`` cada turno ganha um **identificador de execução** e o
logger ``sora.rastro`` registra, em JSON de uma linha:

- ``modelo.pedido``: modelo da vez, quantas mensagens, o papel e o tamanho da última, e os nomes
  das ferramentas oferecidas naquele turno;
- ``modelo.resposta``: as chamadas de ferramenta pedidas (nome, id e as CHAVES dos argumentos),
  o tamanho do texto e o tempo; ``modelo.erro``: o tipo da exceção;
- ``ferramenta.inicio`` / ``ferramenta.fim`` / ``ferramenta.erro`` / ``ferramenta.pausa`` (cartão
  de aprovação ou pergunta): nome, id, tempo e o tamanho do resultado.

Nunca registra chave, token nem imagem. O conteúdo (texto do modelo, valores dos argumentos e
resultados) só entra com ``SORA_RASTRO_CONTEUDO=1``, mascarado (``limpar_texto_sensivel``) e
cortado em ``MAX_CONTEUDO`` caracteres.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage

registro = logging.getLogger("sora.rastro")

MAX_CONTEUDO = 400


def rastro_ligado() -> bool:
    return os.environ.get("SORA_RASTRO", "").strip().lower() in {"1", "true", "sim"}


def _conteudo_ligado() -> bool:
    return os.environ.get("SORA_RASTRO_CONTEUDO", "").strip().lower() in {"1", "true", "sim"}


def _texto(valor: Any) -> str:
    if isinstance(valor, str):
        return valor
    if isinstance(valor, list):
        return " ".join(
            str(parte.get("text", "")) if isinstance(parte, dict) else str(parte) for parte in valor
        )
    return str(valor)


def _mascarado(valor: Any) -> str:
    from app.core.redacao import limpar_texto_sensivel

    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, default=str)
    texto = limpar_texto_sensivel(texto)
    return texto[:MAX_CONTEUDO] + ("…" if len(texto) > MAX_CONTEUDO else "")


def nome_do_modelo(modelo: Any) -> str:
    return str(getattr(modelo, "model", None) or getattr(modelo, "model_name", None) or "?")


def _nome_da_ferramenta(ferramenta: Any) -> str:
    if isinstance(ferramenta, dict):
        return str(ferramenta.get("name") or ferramenta.get("function", {}).get("name") or "?")
    return str(getattr(ferramenta, "name", "?"))


class Rastro:
    """Um por execução do agente (um turno, ou a retomada dele)."""

    def __init__(self, contexto: Any) -> None:
        from app.agentes.middleware.passos import id_do_turno

        self.execucao = str(id_do_turno(contexto))
        self.base = {
            "execucao": self.execucao,
            "agente": str(getattr(contexto, "agente_id", "")),
            "conversa": str(getattr(contexto, "conversa_id", "")),
            "papel": getattr(contexto, "papel", ""),
        }
        self.conteudo = _conteudo_ligado()
        self.chamadas = 0

    def registrar(self, evento: str, **campos: Any) -> None:
        registro.info(
            json.dumps({**self.base, "evento": evento, **campos}, ensure_ascii=False, default=str)
        )


class MiddlewareRastroModelo(AgentMiddleware):  # type: ignore[type-arg]
    """O mais por dentro da lista: vê o pedido que sai para o modelo e a resposta crua dele."""

    def __init__(self, rastro: Rastro) -> None:
        super().__init__()
        self.rastro = rastro

    async def awrap_model_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        self.rastro.chamadas += 1
        mensagens = list(getattr(request, "messages", []) or [])
        ultima = mensagens[-1] if mensagens else None
        campos: dict[str, Any] = {
            "chamada": self.rastro.chamadas,
            "modelo": nome_do_modelo(getattr(request, "model", None)),
            "mensagens": len(mensagens),
            "historico": [
                {"papel": m.type, "chamada_id": m.tool_call_id}
                if isinstance(m, ToolMessage)
                else {"papel": m.type}
                for m in mensagens
            ],
            "ultima": getattr(ultima, "type", None),
            "ultima_chars": len(_texto(getattr(ultima, "content", ""))) if ultima else 0,
            "ferramentas": [_nome_da_ferramenta(f) for f in getattr(request, "tools", []) or []],
        }
        if self.rastro.conteudo and ultima is not None:
            campos["ultima_texto"] = _mascarado(_texto(ultima.content))
        self.rastro.registrar("modelo.pedido", **campos)
        inicio = time.monotonic()
        try:
            resposta = await handler(request)
        except Exception as erro:
            self.rastro.registrar(
                "modelo.erro",
                chamada=self.rastro.chamadas,
                tipo=type(erro).__name__,
                ms=int((time.monotonic() - inicio) * 1000),
            )
            raise
        mensagem = _ultima_ai(resposta)
        ms = int((time.monotonic() - inicio) * 1000)
        saida: dict[str, Any] = {"chamada": self.rastro.chamadas, "ms": ms}
        if mensagem is not None:
            saida["tool_calls"] = [self._chamada(c) for c in (mensagem.tool_calls or [])]
            saida["invalidas"] = len(getattr(mensagem, "invalid_tool_calls", None) or [])
            texto = _texto(mensagem.content)
            saida["texto_chars"] = len(texto)
            if self.rastro.conteudo and texto:
                saida["texto"] = _mascarado(texto)
        self.rastro.registrar("modelo.resposta", **saida)
        return resposta

    def _chamada(self, chamada: dict[str, Any]) -> dict[str, Any]:
        dados: dict[str, Any] = {
            "nome": chamada.get("name"),
            "id": str(chamada.get("id", "")),
            "args": sorted((chamada.get("args") or {}).keys()),
        }
        if self.rastro.conteudo:
            dados["valores"] = _mascarado(chamada.get("args"))
        return dados


class MiddlewareRastroFerramentas(AgentMiddleware):  # type: ignore[type-arg]
    """O mais por fora da lista: vê a chamada como o modelo pediu e o resultado que volta a ele
    (depois de cerca, revisor e conferência), inclusive a pausa para o cartão."""

    def __init__(self, rastro: Rastro) -> None:
        super().__init__()
        self.rastro = rastro

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        from langgraph.errors import GraphBubbleUp

        chamada = request.tool_call
        base = {"nome": chamada.get("name"), "id": str(chamada.get("id", ""))}
        campos = {**base, "args": sorted((chamada.get("args") or {}).keys())}
        if self.rastro.conteudo:
            campos["valores"] = _mascarado(chamada.get("args"))
        self.rastro.registrar("ferramenta.inicio", **campos)
        inicio = time.monotonic()
        try:
            resultado = await handler(request)
        except GraphBubbleUp:
            self.rastro.registrar(
                "ferramenta.pausa", **base, ms=int((time.monotonic() - inicio) * 1000)
            )
            raise
        except Exception as erro:
            self.rastro.registrar(
                "ferramenta.erro",
                **base,
                tipo=type(erro).__name__,
                ms=int((time.monotonic() - inicio) * 1000),
            )
            raise
        fim: dict[str, Any] = {**base, "ms": int((time.monotonic() - inicio) * 1000)}
        if isinstance(resultado, ToolMessage):
            texto = _texto(resultado.content)
            fim["status"] = getattr(resultado, "status", None)
            fim["resultado_chars"] = len(texto)
            if self.rastro.conteudo:
                fim["resultado"] = _mascarado(texto)
        else:
            fim["resultado_tipo"] = type(resultado).__name__
        self.rastro.registrar("ferramenta.fim", **fim)
        return resultado


def _ultima_ai(resposta: Any) -> AIMessage | None:
    candidatas = getattr(resposta, "result", None)
    if candidatas is None:
        candidatas = [resposta]
    for mensagem in reversed(list(candidatas)):
        if isinstance(mensagem, AIMessage):
            return mensagem
    return None
