"""Busca na web (especificação §8.1): provedores, cache de 24 h e limites.

Sem rede: Tavily, Brave e SearXNG respondem por ``httpx.MockTransport``.
"""

import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from uuid import uuid4

import fakeredis
import httpx
import pytest

from app.busca import provedor as p
from app.busca.brave import BuscaBrave, limpar_trecho
from app.busca.falso import RESULTADOS_PADRAO, BuscaFalsa
from app.busca.provedor import (
    CACHE_SEGUNDOS,
    LIMITE_POR_CADEIA,
    LIMITE_POR_USUARIO_DIA,
    ErroBusca,
    LimiteDeBusca,
    ResultadoBusca,
    buscar,
    buscar_com_cache,
    chave_cache,
    chave_uso_dia,
    contar_busca,
    dominio,
    obter_provedor,
)
from app.busca.searxng import BuscaSearxng
from app.busca.tavily import BuscaTavily

CHAVE = "chave-de-teste-nao-real"

RESPOSTA_TAVILY = {
    "query": "café gelado",
    "results": [
        {
            "title": "Café gelado em alta",
            "url": "https://www.exemplo.com.br/cafe",
            "content": "O café gelado cresceu 30% no verão.",
            "score": 0.9,
        },
        {"title": "Sem link", "url": None, "content": "x"},
        {"title": "Receitas", "url": "https://exemplo.org/receitas", "content": "Cold brew."},
    ],
}

RESPOSTA_BRAVE = {
    "web": {
        "results": [
            {
                "title": "Guia do <strong>café</strong>",
                "url": "https://exemplo.net/guia",
                "description": "Tudo sobre <strong>café gelado</strong> &amp; cold brew.",
            }
        ]
    }
}


@pytest.fixture
async def redis() -> AsyncIterator[fakeredis.FakeAsyncRedis]:
    cliente = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield cliente
    await cliente.aclose()


def cliente_que_responde(
    corpo: object, status: int = 200, guardar: list[httpx.Request] | None = None
) -> httpx.AsyncClient:
    def manipulador(requisicao: httpx.Request) -> httpx.Response:
        if guardar is not None:
            guardar.append(requisicao)
        return httpx.Response(status, json=corpo)

    return httpx.AsyncClient(transport=httpx.MockTransport(manipulador))


# ---------- Tavily ----------


async def test_tavily_monta_o_pedido_e_converte() -> None:
    pedidos: list[httpx.Request] = []
    async with cliente_que_responde(RESPOSTA_TAVILY, guardar=pedidos) as cliente:
        resultados = await BuscaTavily(CHAVE, cliente=cliente).buscar("café gelado", limite=5)

    [pedido] = pedidos
    assert pedido.method == "POST"
    assert str(pedido.url) == "https://api.tavily.com/search"
    assert pedido.headers["authorization"] == f"Bearer {CHAVE}"
    corpo = json.loads(pedido.content)
    assert corpo["query"] == "café gelado"
    assert corpo["max_results"] == 5
    assert corpo["country"] == "brazil"

    assert resultados == [
        ResultadoBusca(
            titulo="Café gelado em alta",
            url="https://www.exemplo.com.br/cafe",
            trecho="O café gelado cresceu 30% no verão.",
            origem="exemplo.com.br",
        ),
        ResultadoBusca(
            titulo="Receitas",
            url="https://exemplo.org/receitas",
            trecho="Cold brew.",
            origem="exemplo.org",
        ),
    ]


async def test_tavily_respeita_o_limite() -> None:
    async with cliente_que_responde(RESPOSTA_TAVILY) as cliente:
        resultados = await BuscaTavily(CHAVE, cliente=cliente).buscar("x", limite=1)
    assert len(resultados) == 1


# ---------- Brave ----------


async def test_brave_monta_o_pedido_e_limpa_o_html() -> None:
    pedidos: list[httpx.Request] = []
    async with cliente_que_responde(RESPOSTA_BRAVE, guardar=pedidos) as cliente:
        [resultado] = await BuscaBrave(CHAVE, cliente=cliente).buscar("café gelado")

    [pedido] = pedidos
    assert pedido.method == "GET"
    assert pedido.url.host == "api.search.brave.com"
    assert pedido.headers["x-subscription-token"] == CHAVE
    assert pedido.url.params["q"] == "café gelado"
    assert pedido.url.params["country"] == "BR"
    assert pedido.url.params["search_lang"] == "pt-br"
    assert pedido.url.params["count"] == "5"

    assert resultado.titulo == "Guia do café"
    assert resultado.trecho == "Tudo sobre café gelado & cold brew."
    assert resultado.origem == "exemplo.net"


def test_limpar_trecho() -> None:
    assert limpar_trecho(" <b>a</b> &lt;b&gt; ") == "a <b>"


async def test_brave_sem_resultados_web() -> None:
    async with cliente_que_responde({"query": {}}) as cliente:
        assert await BuscaBrave(CHAVE, cliente=cliente).buscar("x") == []


# ---------- SearXNG ----------


async def test_searxng_pede_json() -> None:
    pedidos: list[httpx.Request] = []
    corpo = {"results": [{"title": "T", "url": "https://exemplo.org/a", "content": "c"}]}
    async with cliente_que_responde(corpo, guardar=pedidos) as cliente:
        [r] = await BuscaSearxng("http://localhost:8888/", cliente=cliente).buscar("x")
    assert str(pedidos[0].url).startswith("http://localhost:8888/search?")
    assert pedidos[0].url.params["format"] == "json"
    assert r.origem == "exemplo.org"


# ---------- erros ----------


@pytest.mark.parametrize(
    ("status", "trecho"),
    [
        (401, "recusada"),
        (403, "recusada"),
        (429, "limite do plano"),
        (432, "limite do plano"),
        (500, "500"),
    ],
)
@pytest.mark.parametrize("classe", [BuscaTavily, BuscaBrave])
async def test_erros_http_viram_erro_busca_sem_vazar_a_chave(
    classe: Callable[..., p.ProvedorBusca], status: int, trecho: str
) -> None:
    async with cliente_que_responde({"detail": "x"}, status=status) as cliente:
        with pytest.raises(ErroBusca, match=trecho) as erro:
            await classe(CHAVE, cliente=cliente).buscar("x")
    assert CHAVE not in str(erro.value)


async def test_falha_de_rede_vira_erro_busca() -> None:
    def manipulador(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rede")

    async with httpx.AsyncClient(transport=httpx.MockTransport(manipulador)) as cliente:
        with pytest.raises(ErroBusca, match="Não consegui"):
            await BuscaTavily(CHAVE, cliente=cliente).buscar("x")


async def test_resposta_que_nao_e_json_vira_erro() -> None:
    transporte = httpx.MockTransport(lambda _: httpx.Response(200, content=b"<html>"))
    async with httpx.AsyncClient(transport=transporte) as cliente:
        with pytest.raises(ErroBusca, match="inválida"):
            await BuscaBrave(CHAVE, cliente=cliente).buscar("x")


def test_repr_nao_mostra_a_chave() -> None:
    assert CHAVE not in repr(BuscaTavily(CHAVE))
    assert CHAVE not in repr(BuscaBrave(CHAVE))


# ---------- obter_provedor ----------


def test_obter_provedor() -> None:
    assert isinstance(obter_provedor("tavily", chave=CHAVE), BuscaTavily)
    assert isinstance(obter_provedor("brave", chave=CHAVE), BuscaBrave)
    assert isinstance(obter_provedor("searxng"), BuscaSearxng)
    assert isinstance(obter_provedor("falso"), BuscaFalsa)


@pytest.mark.parametrize("nome", ["tavily", "brave"])
def test_provedor_pago_sem_chave_e_erro(nome: str) -> None:
    with pytest.raises(ErroBusca, match="BUSCA_CHAVE"):
        obter_provedor(nome)


def test_provedor_desconhecido_e_erro() -> None:
    with pytest.raises(ErroBusca, match="desconhecido"):
        obter_provedor("google")


# ---------- trava de produção (rodada 3, item 11) ----------


@pytest.mark.parametrize("nome", ["falso", "searxng", "FALSO"])
@pytest.mark.parametrize("ambiente", ["producao", "homologacao", ""])
def test_busca_de_desenvolvimento_recusada_em_producao(nome: str, ambiente: str) -> None:
    with pytest.raises(p.BuscaProibidaEmProducao, match="só para desenvolvimento"):
        obter_provedor(nome, ambiente=ambiente)
    with pytest.raises(p.BuscaProibidaEmProducao):
        p.verificar_busca_permitida(nome, ambiente)


@pytest.mark.parametrize("ambiente", ["desenvolvimento", "teste"])
def test_busca_de_desenvolvimento_liberada_local(ambiente: str) -> None:
    assert isinstance(obter_provedor("falso", ambiente=ambiente), BuscaFalsa)
    assert isinstance(obter_provedor("searxng", ambiente=ambiente), BuscaSearxng)


def test_busca_paga_vale_em_producao() -> None:
    assert isinstance(obter_provedor("tavily", chave=CHAVE, ambiente="producao"), BuscaTavily)
    p.verificar_busca_permitida("brave", "producao")


def test_fabrica_le_o_ambiente_da_configuracao(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.core.config as config

    falsa = type("Config", (), {"ambiente": "producao"})()
    monkeypatch.setattr(config, "obter_configuracao", lambda: falsa)
    with pytest.raises(p.BuscaProibidaEmProducao):
        obter_provedor("falso")


@pytest.mark.parametrize(
    ("busca", "recusa"), [("falso", True), ("searxng", True), ("tavily", False)]
)
def test_worker_nao_sobe_com_busca_de_desenvolvimento_em_producao(
    monkeypatch: pytest.MonkeyPatch, busca: str, recusa: bool
) -> None:
    from workers import configuracao

    falsa = type(
        "Config", (), {"ambiente": "producao", "sora_modelo_falso": False, "busca_provedor": busca}
    )()
    monkeypatch.setattr(configuracao, "obter_configuracao", lambda: falsa)
    if recusa:
        with pytest.raises(p.BuscaProibidaEmProducao):
            configuracao.verificar_trava_de_producao()
    else:
        configuracao.verificar_trava_de_producao()


# ---------- falso ----------


async def test_falso_devolve_os_fixos_e_guarda_as_consultas() -> None:
    falso = BuscaFalsa()
    assert await falso.buscar("a", limite=2) == list(RESULTADOS_PADRAO[:2])
    assert falso.consultas == ["a"]


# ---------- cache ----------


async def test_cache_de_24_horas(redis: fakeredis.FakeAsyncRedis) -> None:
    falso = BuscaFalsa()
    primeira = await buscar_com_cache(redis, falso, "falso", "Café  Gelado")
    segunda = await buscar_com_cache(redis, falso, "falso", " café gelado ")
    assert primeira == segunda
    assert falso.consultas == ["Café  Gelado"]  # a 2ª veio do cache
    ttl = await redis.ttl(chave_cache("falso", "café gelado", "pt-BR", 5))
    assert CACHE_SEGUNDOS - 5 <= ttl <= CACHE_SEGUNDOS


def test_chave_de_cache_separa_provedor_idioma_e_limite() -> None:
    chaves = {
        chave_cache("tavily", "x", "pt-BR", 5),
        chave_cache("brave", "x", "pt-BR", 5),
        chave_cache("tavily", "x", "en-US", 5),
        chave_cache("tavily", "x", "pt-BR", 3),
    }
    assert len(chaves) == 4


# ---------- limites ----------


async def test_limite_de_300_por_dia(redis: fakeredis.FakeAsyncRedis) -> None:
    usuario = uuid4()
    await redis.set(chave_uso_dia(usuario), LIMITE_POR_USUARIO_DIA - 1)
    await contar_busca(redis, usuario)  # a 300ª passa
    with pytest.raises(LimiteDeBusca, match="300"):
        await contar_busca(redis, usuario)


async def test_o_dia_seguinte_zera(redis: fakeredis.FakeAsyncRedis) -> None:
    usuario = uuid4()
    hoje = datetime(2026, 10, 14, 23, 59, tzinfo=UTC)
    amanha = datetime(2026, 10, 15, 0, 1, tzinfo=UTC)
    await redis.set(chave_uso_dia(usuario, hoje), LIMITE_POR_USUARIO_DIA)
    await contar_busca(redis, usuario, agora=amanha)
    assert int(await redis.get(chave_uso_dia(usuario, amanha))) == 1
    assert 0 < await redis.ttl(chave_uso_dia(usuario, amanha))


async def test_limite_de_20_por_cadeia(redis: fakeredis.FakeAsyncRedis) -> None:
    usuario, cadeia = uuid4(), uuid4()
    for _ in range(LIMITE_POR_CADEIA):
        await contar_busca(redis, usuario, cadeia)
    with pytest.raises(LimiteDeBusca, match="20"):
        await contar_busca(redis, usuario, cadeia)
    await contar_busca(redis, usuario, uuid4())  # outra cadeia segue


async def test_buscar_conta_e_usa_o_cache(redis: fakeredis.FakeAsyncRedis) -> None:
    falso, usuario = BuscaFalsa(), uuid4()
    for _ in range(2):
        resultados = await buscar(redis, falso, "falso", "x", usuario_id=usuario, limite=2)
    assert len(resultados) == 2
    assert len(falso.consultas) == 1
    assert int(await redis.get(chave_uso_dia(usuario))) == 2


async def test_consulta_vazia_e_erro(redis: fakeredis.FakeAsyncRedis) -> None:
    with pytest.raises(ErroBusca, match="vazia"):
        await buscar(redis, BuscaFalsa(), "falso", "   ", usuario_id=uuid4())


@pytest.mark.parametrize(
    ("url", "esperado"),
    [
        ("https://www.g1.globo.com/a", "g1.globo.com"),
        ("http://exemplo.org", "exemplo.org"),
        ("lixo", ""),
    ],
)
def test_dominio(url: str, esperado: str) -> None:
    assert dominio(url) == esperado
