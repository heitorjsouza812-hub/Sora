"""Sessão do navegador por texto sobre o Playwright (opcional).

Uma sessão por agente e etapa; Chromium sem disco persistente, sem downloads e com todo
pedido de rede conferido pela proteção SSRF (``app/busca/ler_pagina.py``). Adaptado do
Rakazo (github.com/elie222/rakazo, Apache-2.0): ``page-browser-session.ts``.
"""

from __future__ import annotations

from typing import Any

from app.busca.ler_pagina import EnderecoBloqueado, ErroLeitura, validar_destino
from app.ferramentas.base import ErroFerramenta
from app.navegador import (
    ATRIBUTO_REF,
    MAX_ELEMENTOS,
    MAX_NOME_ELEMENTO,
    MAX_TEXTO_PAGINA,
    SCRIPT_SNAPSHOT,
    SELETOR_INTERATIVO,
    AcaoNavegador,
    Snapshot,
    ler_snapshot,
    validar_acao,
)

PRAZO_NAVEGACAO_MS = 20_000
PRAZO_ACAO_MS = 5_000


class SessaoNavegador:
    def __init__(self) -> None:
        self._playwright: Any = None
        self._navegador: Any = None
        self._contexto: Any = None
        self._pagina: Any = None
        self.geracao = 0

    async def abrir_sessao(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError as erro:  # pragma: no cover - depende de instalação opcional
            raise ErroFerramenta(
                "O navegador não está instalado neste servidor (uv sync --group navegador)."
            ) from erro
        self._playwright = await async_playwright().start()
        try:
            self._navegador = await self._playwright.chromium.launch(headless=True)
            self._contexto = await self._navegador.new_context(
                accept_downloads=False,
                java_script_enabled=True,
                locale="pt-BR",
                service_workers="block",
            )
            await self._contexto.route("**/*", self._filtrar_pedido)
            self._pagina = await self._contexto.new_page()
        except Exception as erro:
            await self.fechar()
            raise ErroFerramenta(
                "Não consegui abrir o navegador (rode 'playwright install chromium')."
            ) from erro

    async def _filtrar_pedido(self, rota: Any) -> None:
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

    async def fechar(self) -> None:
        for recurso in (self._contexto, self._navegador):
            if recurso is not None:
                await recurso.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._pagina = self._contexto = self._navegador = self._playwright = None

    async def _garantir(self) -> Any:
        if self._pagina is None:
            await self.abrir_sessao()
        return self._pagina

    async def ler(self) -> Snapshot:
        pagina = await self._garantir()
        self.geracao += 1
        dados = await pagina.evaluate(
            SCRIPT_SNAPSHOT,
            [
                SELETOR_INTERATIVO,
                ATRIBUTO_REF,
                self.geracao,
                MAX_ELEMENTOS,
                MAX_TEXTO_PAGINA,
                MAX_NOME_ELEMENTO,
            ],
        )
        return ler_snapshot(dados)

    async def abrir(self, url: str) -> Snapshot:
        try:
            await validar_destino(url)
        except (EnderecoBloqueado, ErroLeitura) as erro:
            raise ErroFerramenta(f"Endereço recusado: {erro}") from erro
        pagina = await self._garantir()
        try:
            await pagina.goto(url, wait_until="domcontentloaded", timeout=PRAZO_NAVEGACAO_MS)
        except Exception as erro:
            raise ErroFerramenta("Não consegui abrir a página.") from erro
        return await self.ler()

    async def agir(self, acoes: list[AcaoNavegador]) -> Snapshot:
        """Faz as ações em ordem. Para na primeira que falhar e diz o que já foi feito."""
        pagina = await self._garantir()
        for acao in acoes:
            validar_acao(acao, self.geracao)
        feitas = 0
        for acao in acoes:
            try:
                alvo = pagina.locator(f"[{ATRIBUTO_REF}='{acao.ref}']") if acao.ref else None
                if acao.tipo == "clicar":
                    await alvo.click(timeout=PRAZO_ACAO_MS)
                elif acao.tipo == "digitar":
                    await alvo.fill(acao.texto or "", timeout=PRAZO_ACAO_MS)
                elif acao.tipo == "selecionar":
                    await alvo.select_option(acao.texto or "", timeout=PRAZO_ACAO_MS)
                elif acao.tipo == "tecla":
                    await pagina.keyboard.press(acao.tecla or "Enter")
                else:
                    await pagina.mouse.wheel(0, 800)
            except Exception as erro:
                raise ErroFerramenta(
                    f"A ação {feitas + 1} ({acao.tipo}) falhou depois de {feitas} feitas. "
                    "Leia a página antes de continuar e não repita ações já feitas."
                ) from erro
            feitas += 1
        try:
            await pagina.wait_for_load_state("domcontentloaded", timeout=PRAZO_ACAO_MS)
        except Exception:
            pass
        return await self.ler()
