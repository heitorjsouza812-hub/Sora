"""Playwright num loop próprio, para o worker que roda no Windows.

O worker usa o loop "selector" no Windows (o psycopg assíncrono exige), e esse loop não cria
subprocesso, que é como o Playwright fala com o Chromium. Aqui o Playwright vive num loop
"proactor" numa thread dedicada, e cada objeto dele chega ao resto do código embrulhado por uma
``Ponte``: as chamadas assíncronas rodam na thread do Playwright e o resultado volta para o loop
de quem chamou. Em Linux (e em qualquer loop que cria subprocesso) nada disso é usado.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import threading
from collections.abc import Awaitable, Callable
from typing import Any


def precisa_de_loop_proprio() -> bool:
    """Só o Windows com loop sem suporte a subprocesso (o "selector" do worker)."""
    if sys.platform != "win32":
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    return not isinstance(loop, asyncio.ProactorEventLoop)


class LoopDoPlaywright:
    """Uma thread com um loop proactor, para tudo o que é do Playwright."""

    def __init__(self) -> None:
        pronto = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._identificador = 0

        def corpo() -> None:
            loop = asyncio.ProactorEventLoop()  # type: ignore[attr-defined]
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._identificador = threading.get_ident()
            pronto.set()
            try:
                loop.run_forever()
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

        self._thread = threading.Thread(target=corpo, name="playwright-loop", daemon=True)
        self._thread.start()
        pronto.wait()

    def dentro(self) -> bool:
        return threading.get_ident() == self._identificador

    def executar(self, corrotina: Awaitable[Any]) -> Awaitable[Any]:
        """Roda na thread do Playwright; quem chama espera no seu próprio loop."""
        assert self._loop is not None

        async def rodar() -> Any:
            return await corrotina

        futuro = asyncio.run_coroutine_threadsafe(rodar(), self._loop)
        return asyncio.wrap_future(futuro)

    def parar(self) -> None:
        if self._loop is not None and not self.dentro():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=10)


def _do_playwright(valor: Any) -> bool:
    modulo = type(valor).__module__ or ""
    return modulo.startswith("playwright.")


def embrulhar(valor: Any, loop: LoopDoPlaywright) -> Any:
    if isinstance(valor, Ponte):
        return valor
    if isinstance(valor, list):
        return [embrulhar(item, loop) for item in valor]
    if isinstance(valor, tuple):
        return tuple(embrulhar(item, loop) for item in valor)
    if _do_playwright(valor):
        return Ponte(valor, loop)
    return valor


def desembrulhar(valor: Any) -> Any:
    if isinstance(valor, Ponte):
        return object.__getattribute__(valor, "_objeto")
    if isinstance(valor, list):
        return [desembrulhar(item) for item in valor]
    if isinstance(valor, tuple):
        return tuple(desembrulhar(item) for item in valor)
    if isinstance(valor, dict):
        return {chave: desembrulhar(item) for chave, item in valor.items()}
    return valor


class Ponte:
    """Faz um objeto do Playwright (página, contexto, sessão CDP…) valer em qualquer loop."""

    __slots__ = ("_loop", "_objeto")

    def __init__(self, objeto: Any, loop: LoopDoPlaywright) -> None:
        object.__setattr__(self, "_objeto", objeto)
        object.__setattr__(self, "_loop", loop)

    def __getattr__(self, nome: str) -> Any:
        objeto = object.__getattribute__(self, "_objeto")
        loop: LoopDoPlaywright = object.__getattribute__(self, "_loop")
        valor = getattr(objeto, nome)
        if not callable(valor):
            return embrulhar(valor, loop)
        if inspect.iscoroutinefunction(valor):
            return _Assincrono(valor, loop)

        def sincrono(*args: Any, **kwargs: Any) -> Any:
            resultado = valor(*desembrulhar(args), **desembrulhar(kwargs))
            return embrulhar(resultado, loop)

        return sincrono

    def __repr__(self) -> str:
        return f"Ponte({object.__getattribute__(self, '_objeto')!r})"


class _Assincrono:
    def __init__(self, funcao: Callable[..., Awaitable[Any]], loop: LoopDoPlaywright) -> None:
        self._funcao = funcao
        self._loop = loop

    def __call__(self, *args: Any, **kwargs: Any) -> Awaitable[Any]:
        a, k = desembrulhar(args), desembrulhar(kwargs)
        if self._loop.dentro():
            return self._chamar_dentro(a, k)
        return self._chamar_fora(a, k)

    async def _chamar_dentro(self, a: Any, k: Any) -> Any:
        return embrulhar(await self._funcao(*a, **k), self._loop)

    async def _chamar_fora(self, a: Any, k: Any) -> Any:
        resultado = await self._loop.executar(self._funcao(*a, **k))
        return embrulhar(resultado, self._loop)
