"""Ferramentas de leitura do Prumo sem rede nem banco: SSRF, cerca única e imagem falsa."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.busca import ler_pagina as leitor
from app.busca.provedor import ResultadoBusca
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.buscar_web import formatar_resultados
from app.ferramentas.ler_anexo import extrair_do_anexo
from app.ferramentas.ler_pagina import LerPagina, ler_pagina
from app.llm.imagem import png_liso

CTX = ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4())


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://10.0.0.5:8080/",
        "file:///etc/passwd",
        "https://usuario:senha@exemplo.com/",
    ],
)
async def test_ler_pagina_recusa_enderecos_internos(url: str, monkeypatch) -> None:
    class RedisFalso:
        async def get(self, _):
            return None

        async def set(self, *_a, **_k):
            raise AssertionError("não deveria guardar nada")

    monkeypatch.setattr("app.ferramentas.ler_pagina.obter_redis", lambda: RedisFalso())
    with pytest.raises(ErroFerramenta):
        await ler_pagina(LerPagina(url=url), CTX)


async def test_ler_pagina_devolve_texto_sem_cerca(monkeypatch) -> None:
    async def lida(url, *, redis=None, **_):
        return leitor.PaginaLida(
            url=url, url_final=url, titulo="Café", texto="Texto da página.", tipo="text/html"
        )

    monkeypatch.setattr("app.ferramentas.ler_pagina.obter_redis", lambda: None)
    monkeypatch.setattr(leitor, "ler_pagina", lida)
    resposta = await ler_pagina(LerPagina(url="https://exemplo.com.br/"), CTX)
    assert "Texto da página." in resposta
    assert "<dado_externo" not in resposta  # a cerca é do MiddlewareCerca (uma vez só)


def test_formatar_resultados() -> None:
    assert formatar_resultados([]) == "Nenhum resultado encontrado."
    texto = formatar_resultados(
        [ResultadoBusca(titulo="A", url="https://a.com/x", trecho="trecho", origem="a.com")]
    )
    assert texto == "1. A\n   https://a.com/x (a.com)\n   trecho"


def test_extrair_texto_e_json_formatado() -> None:
    assert extrair_do_anexo(b"oi", "text/plain", "a.txt") == "oi"
    assert '"a": 1' in extrair_do_anexo(b'{"a":1}', "application/json", "a.json")
    with pytest.raises(ErroFerramenta):
        extrair_do_anexo(b"\x00", "application/zip", "a.zip")


def test_png_liso_e_valido() -> None:
    png = png_liso(4, 4, (1, 2, 3))
    assert png.startswith(b"\x89PNG\r\n\x1a\n") and png.endswith(b"IEND\xaeB`\x82")
