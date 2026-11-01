"""Motor Playwright do navegador persistente (opcional: ``uv sync --group navegador``).

Um Chromium por worker e um *contexto* por partição (perfil). O estado de login de cada
partição vem do banco (cifrado, ``app/navegador/perfis.py``) ao abrir o contexto e volta para o
banco ao fechar o contexto ou a cada ``salvar_estados``. Todo pedido de rede passa pela mesma
proteção SSRF do ``ler_pagina``; downloads ficam desligados.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from app.busca.ler_pagina import EnderecoBloqueado, ErroLeitura, validar_destino
from app.ferramentas.base import ErroFerramenta
from app.navegador.abas import Aba

PRAZO_NAVEGACAO_MS = 20_000

LerEstado = Callable[[str], Awaitable[dict[str, Any] | None]]
GravarEstado = Callable[[str, dict[str, Any]], Awaitable[None]]
AoConsole = Callable[[UUID, str, str], None]


class MotorPlaywright:  # pragma: no cover - depende do Chromium instalado
    def __init__(
        self, *, ler_estado: LerEstado, gravar_estado: GravarEstado, ao_console: AoConsole
    ) -> None:
        self._ler_estado = ler_estado
        self._gravar_estado = gravar_estado
        self._ao_console = ao_console
        self._playwright: Any = None
        self._navegador: Any = None
        self._contextos: dict[str, Any] = {}
        self._paginas: dict[UUID, Any] = {}

    async def _iniciar(self) -> None:
        if self._navegador is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as erro:
            raise ErroFerramenta(
                "O navegador não está instalado neste servidor (uv sync --group navegador)."
            ) from erro
        self._playwright = await async_playwright().start()
        self._navegador = await self._playwright.chromium.launch(headless=True)

    async def _contexto(self, particao_: str) -> Any:
        await self._iniciar()
        contexto = self._contextos.get(particao_)
        if contexto is None:
            estado = await self._ler_estado(particao_)
            contexto = await self._navegador.new_context(
                accept_downloads=False,
                locale="pt-BR",
                service_workers="block",
                storage_state=estado,
            )
            await contexto.route("**/*", self._filtrar)
            self._contextos[particao_] = contexto
        return contexto

    async def _filtrar(self, rota: Any) -> None:
        url = rota.request.url
        if url.startswith(("data:", "blob:", "about:")):
            await rota.continue_()
            return
        try:
            await validar_destino(url)
        except (EnderecoBloqueado, ErroLeitura):
            await rota.abort("blockedbyclient")
            return
        await rota.continue_()

    async def abrir_pagina(self, aba: Aba) -> None:
        contexto = await self._contexto(aba.particao)
        pagina = await contexto.new_page()
        pagina.on("console", lambda m: self._ao_console(aba.id, m.type, m.text))
        self._paginas[aba.id] = pagina

    def pagina(self, aba: Aba) -> Any:
        """Página carregada da aba (para o navegador por árvore, ``app/navegador/arvore``).

        Chame depois de ``GerenteAbas.usar``, que recarrega a aba se ela foi descarregada.
        """
        pagina = self._paginas.get(aba.id)
        if pagina is None:
            raise ErroFerramenta("Essa aba não está carregada. Use a aba de novo.")
        return pagina

    async def navegar(self, aba: Aba, url: str) -> tuple[str, str]:
        try:
            await validar_destino(url)
        except (EnderecoBloqueado, ErroLeitura) as erro:
            raise ErroFerramenta(f"Endereço recusado: {erro}") from erro
        pagina = self._paginas[aba.id]
        try:
            await pagina.goto(url, wait_until="domcontentloaded", timeout=PRAZO_NAVEGACAO_MS)
        except Exception as erro:
            raise ErroFerramenta("Não consegui abrir a página.") from erro
        return pagina.url, await pagina.title()

    async def descarregar(self, aba: Aba) -> None:
        pagina = self._paginas.pop(aba.id, None)
        if pagina is not None:
            await pagina.close()

    async def fechar(self, aba: Aba) -> None:
        await self.descarregar(aba)

    async def capturar(self, aba: Aba) -> bytes:
        pagina = self._paginas[aba.id]
        return await pagina.screenshot(type="png", full_page=False)

    async def limpar_particao(self, particao_: str) -> None:
        contexto = self._contextos.pop(particao_, None)
        if contexto is not None:
            await contexto.close()
        await self._gravar_estado(particao_, {"cookies": [], "origins": []})

    async def salvar_estados(self) -> None:
        for particao_, contexto in self._contextos.items():
            await self._gravar_estado(particao_, await contexto.storage_state())

    async def encerrar(self) -> None:
        await self.salvar_estados()
        for contexto in self._contextos.values():
            await contexto.close()
        self._contextos.clear()
        self._paginas.clear()
        if self._navegador is not None:
            await self._navegador.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._navegador = self._playwright = None
