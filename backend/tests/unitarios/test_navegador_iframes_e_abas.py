"""Navegador por árvore com Chromium real: iframes e aba nova aberta pelo site.

Antes: o conteúdo de iframe (pagamento embutido, formulário, banner de cookies, login de outro
site) não aparecia na leitura e não dava para clicar; e um link ``target=_blank`` abria uma aba
que o bot não via (a resposta dizia que a página não tinha mudado)."""

from __future__ import annotations

from typing import Any

import pytest

from app.navegador.arvore import NavegadorArvore
from app.navegador.arvore.ferramentas import para_modelo
from app.navegador.arvore.resposta import Codigo
from tests.unitarios.test_navegador_arvore import _refs, pagina  # noqa: F401

SITE = "http://sora.test"
FORM_IFRAME = (
    "<label>Cartao <input id=c></label>"
    "<button onclick=&quot;document.body.insertAdjacentHTML('beforeend','<p>pago</p>')&quot;>"
    "Pagar</button>"
)
PRINCIPAL = f"""<!doctype html><title>Loja</title>
<style>body{{margin:0}} iframe{{border:4px solid #999;padding:6px;margin:40px 0 0 120px}}</style>
<h1>Loja</h1>
<a href="/b" target="_blank">Abrir em nova aba</a>
<iframe title="Pagamento" width="420" height="160" srcdoc="{FORM_IFRAME}"></iframe>
<iframe title="Outro site" width="300" height="120" src="http://outro.test/frame"></iframe>
<iframe title="pixel" width="1" height="1" srcdoc="<button>invisivel</button>"></iframe>
"""
DE_FORA = "<!doctype html><button onclick=\"document.title='clicado'\">Aceitar cookies</button>"
PAGINA_B = "<!doctype html><title>B</title><h1>Pagina B</h1>"


@pytest.fixture
async def loja(pagina: Any) -> Any:  # noqa: F811
    async def servir(route: Any) -> None:
        url = route.request.url
        corpo = PAGINA_B if url.endswith("/b") else DE_FORA if "outro.test" in url else PRINCIPAL
        await route.fulfill(body=corpo, content_type="text/html; charset=utf-8")

    await pagina.context.route("**/*", servir)
    await pagina.goto(f"{SITE}/a")
    return pagina


def _quadro(aba: Any, trecho: str) -> Any:
    return next(f for f in aba.frames if trecho in (f.url or "") or trecho == f.name)


async def test_iframes_visiveis_entram_na_leitura_e_o_pixel_nao(loja: Any) -> None:
    nav = NavegadorArvore(loja)
    resposta = await nav.observar()
    assert resposta.ok, resposta.para_json()
    texto = para_modelo(resposta)
    assert 'iframe "Pagamento"' in texto and 'button "Pagar"' in texto
    assert 'iframe "Outro site"' in texto and 'button "Aceitar cookies"' in texto
    assert "invisivel" not in texto
    assert resposta.dados["iframes"] == ["Pagamento", "Outro site"]


async def test_clicar_e_digitar_dentro_do_iframe(loja: Any) -> None:
    nav = NavegadorArvore(loja)
    refs = _refs((await nav.observar()).dados["arvore"])
    digitou = await nav.agir(refs[("textbox", "Cartao")][0], "digitar", texto="4111")
    assert digitou.ok, digitou.para_json()
    pagou = await nav.agir(refs[("button", "Pagar")][0], "clicar")
    assert pagou.ok, pagou.para_json()
    quadro = next(f for f in loja.frames if f is not loja.main_frame and "about:srcdoc" in f.url)
    assert await quadro.evaluate("document.getElementById('c').value") == "4111"
    assert "pago" in await quadro.evaluate("document.body.innerText")
    # o clique veio do mouse de verdade, no ponto certo (borda e padding do iframe somados)
    assert pagou.dados["passos"][0]["mecanismo"] == "fisico"


async def test_clicar_em_iframe_de_outro_site(loja: Any) -> None:
    nav = NavegadorArvore(loja)
    refs = _refs((await nav.observar()).dados["arvore"])
    r = await nav.agir(refs[("button", "Aceitar cookies")][0], "clicar")
    assert r.ok, r.para_json()
    assert await _quadro(loja, "outro.test").evaluate("document.title") == "clicado"


async def test_ref_de_iframe_que_saiu_da_pagina_e_velha(loja: Any) -> None:
    nav = NavegadorArvore(loja)
    refs = _refs((await nav.observar()).dados["arvore"])
    await loja.evaluate("document.querySelector('iframe[title=Pagamento]').remove()")
    r = await nav.agir(refs[("button", "Pagar")][0], "clicar")
    assert not r.ok and r.erro is not None and r.erro.codigo is Codigo.REF_VELHA


async def test_depois_do_iframe_o_proximo_comando_volta_para_a_pagina(loja: Any) -> None:
    nav = NavegadorArvore(loja)
    refs = _refs((await nav.observar()).dados["arvore"])
    assert (await nav.agir(refs[("button", "Pagar")][0], "clicar")).ok
    achou = await nav.procurar(texto="Loja")
    assert achou.ok and achou.dados["total"] >= 1, achou.para_json()


async def test_clique_que_abre_aba_nova_avisa_o_bot(loja: Any) -> None:
    nav = NavegadorArvore(loja)
    refs = _refs((await nav.observar()).dados["arvore"])
    r = await nav.agir(refs[("link", "Abrir em nova aba")][0], "clicar")
    assert r.ok, r.para_json()
    assert r.dados["aba_nova"]["url"] == f"{SITE}/b"
    assert r.dados["entrega"]["entrega"] == "entregue_confirmada"
    assert r.dados["confirmado_por"] == "abriu_aba"


async def test_procurar_acha_dentro_do_iframe_quando_a_pagina_nao_tem(loja: Any) -> None:
    nav = NavegadorArvore(loja)
    achou = await nav.procurar(papel="button", nome="Aceitar cookies")
    assert achou.ok and achou.dados["total"] == 1, achou.para_json()
    assert achou.dados["iframe"] == "Outro site"
    ref = achou.dados["correspondencias"][0]["ref"]
    assert (await nav.agir(ref, "clicar")).ok
    assert await _quadro(loja, "outro.test").evaluate("document.title") == "clicado"


async def test_texto_para_o_modelo_conta_dos_iframes(loja: Any) -> None:
    texto = para_modelo(await NavegadorArvore(loja).observar())
    assert 'Inclui o conteúdo de iframe: "Pagamento", "Outro site"' in texto


# ------------------------------------------------ casos achados no teste ao vivo (example.com)

BEIRADA = """<!doctype html><title>Beirada</title>
<div style="height:calc(100vh - 1px)"></div><a href="/lenta">Saiba mais</a>
<div style="height:600px"></div>"""


@pytest.fixture
async def beirada(pagina: Any) -> Any:  # noqa: F811
    import asyncio

    async def servir(route: Any) -> None:
        if route.request.url.endswith("/lenta"):
            await asyncio.sleep(0.8)  # servidor de verdade: a URL só muda quando a resposta chega
            await route.fulfill(body=PAGINA_B, content_type="text/html; charset=utf-8")
            return
        await route.fulfill(body=BEIRADA, content_type="text/html; charset=utf-8")

    await pagina.context.route("**/*", servir)
    await pagina.goto(f"{SITE}/beirada")
    return pagina


async def test_link_com_1px_na_beirada_rola_e_clica_com_o_mouse(beirada: Any) -> None:
    """Antes o clique de mouse era pulado (nenhum ponto alcançável) e caía no click() do DOM."""
    nav = NavegadorArvore(beirada)
    refs = _refs((await nav.observar()).dados["arvore"])
    r = await nav.agir(refs[("link", "Saiba mais")][0], "clicar")
    assert r.ok, r.para_json()
    assert r.dados["rolagem_preparatoria"] is True
    assert [p["mecanismo"] for p in r.dados["passos"]] == ["fisico"]


async def test_navegacao_lenta_ainda_confirma_pelo_endereco(beirada: Any) -> None:
    """Antes a resposta olhava a URL só 50 ms depois: link de site real voltava sem confirmar."""
    nav = NavegadorArvore(beirada)
    refs = _refs((await nav.observar()).dados["arvore"])
    r = await nav.agir(refs[("link", "Saiba mais")][0], "clicar")
    assert r.dados["navegou"]["para"] == f"{SITE}/lenta", r.para_json()
    assert r.dados["confirmado_por"] == "navegou"
