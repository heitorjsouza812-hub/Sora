"""Interrupção durante chamadas e fontes do turno, isoladas por execução."""

import asyncio
import json
import re
from contextlib import suppress
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from langchain.agents.middleware import AgentMiddleware
from langchain_core.callbacks import AsyncCallbackHandler

from app.agentes.middleware.cancelamento import CadeiaCancelada

fontes_do_turno: ContextVar[list[dict] | None] = ContextVar("fontes_do_turno", default=None)


def chave_parar(conversa_id: Any) -> str:
    return f"conversa:parar:{conversa_id}"


def _fonte_invalida(partes) -> bool:  # type: ignore[no-untyped-def]
    """Página de erro/bloqueio do buscador e endereço sem domínio de verdade não são fontes."""
    host = (partes.hostname or "").lower()
    if "." not in host or host.endswith("."):
        return True
    caminho = partes.path.lower()
    if host.endswith("duckduckgo.com") and ("static-pages" in caminho or "error" in caminho):
        return True
    return caminho.rstrip("/").endswith("/captcha")


def coletar_fontes(texto: str, fontes: list[dict]) -> None:
    titulo = ""
    for linha in texto.replace("\\n", "\n").splitlines():
        if linha.startswith("Título: "):
            titulo = linha.removeprefix("Título: ").strip()
        elif re.match(r"\d+\. ", linha):
            titulo = re.sub(r"^\d+\. ", "", linha).strip()
        for encontrada in re.findall(r"https?://[^\s<>\"'\\]+", linha):
            url = encontrada.rstrip(".,;)]}")
            try:
                partes = urlsplit(url)
                dominio = partes.hostname
            except ValueError:
                continue
            if not partes.hostname or partes.username or partes.password:
                continue
            if _fonte_invalida(partes):
                continue
            url = urlunsplit(
                (partes.scheme.lower(), partes.netloc.lower(), partes.path, partes.query, "")
            )
            if len(fontes) >= 10 or any(f["url"] == url for f in fontes):
                continue
            fontes.append(
                dict(n=len(fontes) + 1, titulo=titulo or dominio, url=url, dominio=dominio)
            )


class TextoParcial(AsyncCallbackHandler):
    def __init__(self, fluxo=None):
        self.fluxo = fluxo
        self.chamadas = {}
        self.texto = ""
        self.argumentos = ""

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        self.texto += token
        chunk = kwargs.get("chunk")
        mensagem = getattr(chunk, "message", None)
        for chamada in getattr(mensagem, "tool_call_chunks", []) or []:
            indice = chamada.get("index", 0)
            acumulada = self.chamadas.setdefault(indice, {"nome": "", "args": ""})
            if chamada.get("name"):
                acumulada["nome"] = chamada["name"]
            acumulada["args"] += chamada.get("args") or ""
            if acumulada["nome"] in {"falar", "canal_resultado"}:
                self.argumentos = acumulada["args"]
        if self.fluxo is not None:
            await self.fluxo.publicar(self.parcial())

    def parcial(self) -> str:
        from langchain_core.utils.json import parse_partial_json

        with suppress(ValueError, TypeError):
            args = parse_partial_json(self.argumentos)
            if isinstance(args, dict) and isinstance(args.get("texto"), str):
                return args["texto"]
        return self.texto


class MiddlewareConversa(AgentMiddleware):
    def __init__(self, contexto):
        self.contexto = contexto
        self.fontes: list[dict] = []
        self.versao = None
        self.iniciado = False
        self.interrompida = False

    async def _vigiar(self, chamada, parcial=None):
        from app.ferramentas.infra import obter_redis
        from app.orquestrador.cadeia import chave_de_cancelamento

        redis = obter_redis()
        chave = chave_parar(self.contexto.conversa_id)
        if not self.iniciado:
            self.versao = await redis.get(chave)
            self.iniciado = True
            pedido = await self._pedido()
            if pedido is not None and (not pedido.visivel or pedido.estado == "interrompida"):
                await self._salvar_interrompida("")
                raise CadeiaCancelada("Resposta interrompida antes da chamada.")
        tarefa = asyncio.create_task(chamada())
        try:
            while True:
                cancelada = await redis.get(chave) != self.versao
                if self.contexto.cadeia_id:
                    cancelada |= bool(
                        await redis.get(chave_de_cancelamento(self.contexto.cadeia_id))
                    )
                if cancelada:
                    tarefa.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await tarefa
                    await self._salvar_interrompida(parcial.parcial() if parcial else "")
                    raise CadeiaCancelada("Resposta interrompida pelo usuário.")
                pronta, _ = await asyncio.wait({tarefa}, timeout=0.1)
                if pronta:
                    return tarefa.result()
        finally:
            if not tarefa.done():
                tarefa.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await tarefa

    async def _salvar_interrompida(self, texto):
        from app.ferramentas.base import ContextoFerramenta
        from app.ferramentas.falar import Falar, falar

        if self.interrompida:
            return
        self.interrompida = True
        pedido = await self._pedido()
        if pedido is not None and not pedido.visivel:
            return
        token = fontes_do_turno.set(self.fontes)
        try:
            await falar(
                Falar(texto=texto or "Resposta interrompida."),
                ContextoFerramenta(
                    usuario_id=self.contexto.usuario_id,
                    agente_id=self.contexto.agente_id,
                    conversa_id=self.contexto.conversa_id,
                ),
                estado="interrompida",
            )
        finally:
            fontes_do_turno.reset(token)

    async def _pedido(self):
        from uuid import UUID

        from app.ferramentas.infra import abrir_sessao
        from app.modelos.tabelas import Mensagem

        thread = self.contexto.thread_proprio or ""
        if ":pedido:" not in thread:
            return None
        async with abrir_sessao() as sessao:
            return await sessao.get(Mensagem, UUID(thread.rsplit(":pedido:", 1)[1]))

    async def awrap_model_call(self, request, handler):
        from app.agentes.streaming import FluxoTexto

        fluxo = FluxoTexto(self.contexto)
        parcial = TextoParcial(fluxo)
        anteriores = request.model.callbacks
        if anteriores is not None and not isinstance(anteriores, list):
            callbacks = anteriores.copy()
            callbacks.add_handler(parcial)
        else:
            callbacks = [*(anteriores or []), parcial]
        atributos = {"callbacks": callbacks}
        if "streaming" in type(request.model).model_fields:
            atributos["streaming"] = True
        modelo = request.model.model_copy(update=atributos)
        try:
            return await self._vigiar(lambda: handler(request.override(model=modelo)), parcial)
        finally:
            await fluxo.publicar(parcial.parcial(), fim=True)

    async def awrap_tool_call(self, request, handler):
        token = fontes_do_turno.set(self.fontes)
        try:
            resultado = await self._vigiar(lambda: handler(request))
            nome = request.tool_call["name"]
            if nome in {"buscar_web", "ler_pagina"} or nome.startswith("navegador_"):
                conteudo = getattr(resultado, "content", "")
                coletar_fontes(
                    conteudo if isinstance(conteudo, str) else json.dumps(conteudo), self.fontes
                )
                if self.fontes and hasattr(resultado, "content"):
                    return resultado.model_copy(
                        update={
                            "content": str(conteudo)
                            + "\nFontes para citação: "
                            + json.dumps(self.fontes, ensure_ascii=False)
                        }
                    )
            return resultado
        finally:
            fontes_do_turno.reset(token)


class MiddlewareStreamingCanal(MiddlewareConversa):
    """O worker de grupo controla cancelamento e persistencia do resultado."""

    async def _vigiar(self, chamada, parcial=None):
        return await chamada()
