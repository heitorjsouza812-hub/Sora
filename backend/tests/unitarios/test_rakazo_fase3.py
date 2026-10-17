"""Peças da fase 3 adaptadas do Rakazo (docs/referencias/rakazo.md): conectores MCP, canal
Telegram, voz, navegador por texto, computador isolado, gráficos e busca sem chave.

Sem rede: tudo por ``httpx.MockTransport``, clientes falsos e resolvedor de DNS falso.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import fakeredis
import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ValidationError

from app.api import canais as canais_api
from app.busca.duckduckgo import BuscaDuckDuckGo, desembrulhar, ler_resultados
from app.busca.provedor import BuscaProibidaEmProducao, ErroBusca, obter_provedor
from app.canais import telegram as tg
from app.computador import (
    ExecutarComando,
    ResultadoComando,
    SandboxDocker,
    SandboxFalso,
    cortar,
    obter_sandbox,
)
from app.conectores.nomes import nome_conector, nomes_unicos, normalizar, slug_servidor
from app.conectores.servidores import (
    AdicionarServidorMCP,
    ServidorMCP,
    carregar_ferramentas,
    embrulhar,
    montar_conexoes,
    validar_servidor,
)
from app.ferramentas.base import ErroFerramenta
from app.ferramentas.gerar_grafico import GerarGrafico, gerar_grafico
from app.navegador import (
    AcaoNavegador,
    conferir_ref,
    formatar_snapshot,
    ler_snapshot,
    validar_acao,
)
from app.voz.provedores import ErroVoz, VozElevenLabs, VozOpenAI, obter_voz
from app.voz.texto import falavel, frases

TOKEN = "123456789:AAH-segredoDoBotDoTelegram_abcdefghijk"


# ---------- conectores: nomes ----------


def test_nomes_de_ferramenta() -> None:
    assert normalizar("Criar Página!") == "Criar_Pagina"
    assert normalizar("!!!") == "ferramenta"
    assert slug_servidor("Meu__Notion") == "meu_notion"
    assert nome_conector("Notion", "buscar") == "mcp__notion__buscar"
    assert len(nome_conector("servidor", "x" * 200)) == 64
    assert nomes_unicos(["a b", "a_b", "a_b"]) == ["a_b_2", "a_b", "a_b_3"]


# ---------- conectores: servidor ----------


async def _resolver_publico(host: str, porta: int) -> list[str]:
    return ["93.184.216.34"]


async def _resolver_interno(host: str, porta: int) -> list[str]:
    return ["10.0.0.5"]


async def test_validar_servidor() -> None:
    assert await validar_servidor("https://mcp.notion.com/mcp", resolver=_resolver_publico)
    with pytest.raises(ErroFerramenta, match="https"):
        await validar_servidor("http://mcp.exemplo.com", resolver=_resolver_publico)
    with pytest.raises(ErroFerramenta, match="recusado"):
        await validar_servidor("https://interno.exemplo.com", resolver=_resolver_interno)
    with pytest.raises(ErroFerramenta):
        await validar_servidor("https://u:p@mcp.exemplo.com", resolver=_resolver_publico)
    assert await validar_servidor("http://localhost:8000/mcp", ambiente_local=True)
    with pytest.raises(ErroFerramenta):
        await validar_servidor("http://localhost:8000/mcp")


def test_cabecalhos_do_servidor() -> None:
    AdicionarServidorMCP(nome="n", url="https://x.com", cabecalhos={"Authorization": "Bearer t"})
    for ruim in ({"Host": "x"}, {"X": "a\r\nB: c"}, {f"h{i}": "v" for i in range(11)}):
        with pytest.raises(ValidationError):
            AdicionarServidorMCP(nome="n", url="https://x.com", cabecalhos=ruim)


def test_montar_conexoes() -> None:
    conexoes = montar_conexoes(
        [ServidorMCP(nome="Notion", url="https://a.com", cabecalhos={"A": "b"})]
    )
    assert conexoes["notion"]["transport"] == "streamable_http"
    assert conexoes["notion"]["headers"] == {"A": "b"}
    assert "httpx_client_factory" in conexoes["notion"]
    local = montar_conexoes([ServidorMCP(nome="L", url="http://localhost:1")], ambiente_local=True)
    assert "httpx_client_factory" not in local["l"]
    with pytest.raises(ErroFerramenta):
        montar_conexoes([ServidorMCP(nome=f"s{i}", url="https://a.com") for i in range(11)])


class _Consulta(BaseModel):
    consulta: str


def _ferramenta_mcp(
    nome: str, resposta: Any = "ok", erro: Exception | None = None
) -> StructuredTool:
    async def rodar(consulta: str) -> Any:
        if erro:
            raise erro
        return resposta

    return StructuredTool.from_function(
        coroutine=rodar,
        name=nome,
        description=f"faz {nome}",
        args_schema=_Consulta,
        metadata={"readOnlyHint": True},
    )


async def test_embrulho_cerca_corta_e_esconde_segredo() -> None:
    embrulhada = embrulhar(
        _ferramenta_mcp("buscar", "<dado_externo>oi"), "notion", "mcp__notion__buscar"
    )
    resultado = await embrulhada.ainvoke({"consulta": "x"})
    assert resultado.startswith('<dado_externo origem="conector:notion">')
    assert "&lt;dado_externo>oi" in resultado
    assert embrulhada.metadata["grupo"] == "notion" and embrulhada.metadata["readOnlyHint"]
    grande = embrulhar(_ferramenta_mcp("b", "x" * 30_000), "s", "mcp__s__b")
    assert "[… resultado cortado]" in await grande.ainvoke({"consulta": "x"})
    falha = embrulhar(
        _ferramenta_mcp("b", erro=RuntimeError("token=abc123 caiu")), "s", "mcp__s__b"
    )
    with pytest.raises(ErroFerramenta) as erro:
        await falha.ainvoke({"consulta": "x"})
    assert "abc123" not in str(erro.value)


class _ClienteMCPFalso:
    def __init__(self, por_servidor: dict[str, list[StructuredTool]]) -> None:
        self.por_servidor = por_servidor

    async def get_tools(self, *, server_name: str) -> list[StructuredTool]:
        if server_name not in self.por_servidor:
            raise ConnectionError("fora do ar")
        return self.por_servidor[server_name]


async def test_carregar_ferramentas_de_varios_servidores() -> None:
    cliente = _ClienteMCPFalso(
        {
            "notion": [_ferramenta_mcp("buscar"), _ferramenta_mcp("buscar")],
            "drive": [_ferramenta_mcp("listar arquivos")],
        }
    )
    servidores = [ServidorMCP(nome=n, url="https://a.com") for n in ("Notion", "Drive", "Caido")]
    ferramentas = await carregar_ferramentas(servidores, cliente=cliente)
    assert [f.name for f in ferramentas] == [
        "mcp__notion__buscar",
        "mcp__notion__buscar_2",
        "mcp__drive__listar_arquivos",
    ]
    muitas = _ClienteMCPFalso({"n": [_ferramenta_mcp(f"f{i}") for i in range(25)]})
    meta = await carregar_ferramentas([ServidorMCP(nome="n", url="https://a.com")], cliente=muitas)
    assert meta[0].name == "conectores_buscar_ferramentas"
    assert await carregar_ferramentas([], cliente=cliente) == []


# ---------- Telegram ----------


def _atualizacao(texto: Any = "oi", tipo: str = "private", bot: bool = False) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 7,
            "chat": {"id": 42, "type": tipo},
            "from": {"id": 9, "is_bot": bot, "first_name": "Ana"},
            "text": texto,
        },
    }


def test_webhook_e_leitura() -> None:
    assert tg.webhook_autentico("abc", "abc")
    assert not tg.webhook_autentico("abd", "abc")
    assert not tg.webhook_autentico(None, "abc") and not tg.webhook_autentico("", "")
    mensagem = tg.ler_atualizacao(_atualizacao(" oi "))
    assert mensagem is not None and mensagem.chat_id == "42" and mensagem.texto == "oi"
    assert tg.ler_atualizacao(_atualizacao(tipo="group")) is None
    assert tg.ler_atualizacao(_atualizacao(bot=True)) is None
    assert tg.ler_atualizacao(_atualizacao(texto=None)) is None
    assert tg.ler_atualizacao({"edited_message": {}}) is None
    assert tg.codigo_do_start("/start abcd2345") == "ABCD2345"
    assert tg.codigo_do_start("/start@SoraBot ABCD2345") == "ABCD2345"
    assert tg.codigo_do_start("/start") is None


def test_texto_para_o_telegram() -> None:
    assert tg.markdown_para_texto("## Título\n**forte** [site](https://a.com)") == (
        "Título\nforte site (https://a.com)"
    )
    pedacos = tg.dividir(("parágrafo " * 300 + "\n\n") * 3, 4096)
    assert all(len(p) <= 4096 for p in pedacos) and len(pedacos) >= 2
    assert tg.dividir("x" * 5000, 4096) == ["x" * 4096, "x" * 904]
    assert len(tg.gerar_codigo()) == 8 and not set(tg.gerar_codigo()) & set("01IO")


async def test_codigo_de_vinculo_uso_unico() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    usuario = uuid4()
    codigo = await tg.criar_codigo_vinculo(redis, usuario)
    assert await redis.ttl(f"canal:telegram:vinculo:{codigo}") > 0
    assert await tg.usar_codigo_vinculo(redis, codigo.lower()) == usuario
    assert await tg.usar_codigo_vinculo(redis, codigo) is None


async def test_cliente_telegram_corta_e_esconde_token() -> None:
    enviados: list[dict[str, Any]] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        enviados.append(json.loads(pedido.content))
        return httpx.Response(200, json={"ok": True, "result": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http:
        cliente = tg.ClienteTelegram(TOKEN, cliente=http)
        assert await cliente.enviar("42", "a" * 5000) == 2
    assert [len(e["text"]) for e in enviados] == [4096, 904]

    def recusar(pedido: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": f"bad token {TOKEN}"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(recusar)) as http:
        with pytest.raises(tg.ErroTelegram) as erro:
            await tg.ClienteTelegram(TOKEN, cliente=http).enviar("42", "oi")
    assert TOKEN not in str(erro.value)
    with pytest.raises(tg.ErroTelegram):
        await tg.ClienteTelegram(TOKEN).registrar_webhook("http://a.com", "s")


@pytest.fixture
def api_telegram(monkeypatch: pytest.MonkeyPatch) -> Any:
    from app.api import canais
    from app.core.config import obter_configuracao
    from app.main import criar_aplicacao

    monkeypatch.setenv("TELEGRAM_TOKEN_BOT", TOKEN)
    monkeypatch.setenv("TELEGRAM_SEGREDO_WEBHOOK", "segredo-do-webhook")
    obter_configuracao.cache_clear()
    estado: dict[str, Any] = {"enviados": [], "vinculos": {}, "jobs": []}

    async def enviar(self: Any, chat_id: str, texto: str) -> int:
        estado["enviados"].append((chat_id, texto))
        return 1

    async def digitando(self: Any, chat_id: str) -> None:
        return None

    async def vincular(usuario_id: Any, chat_id: str) -> None:
        estado["vinculos"][chat_id] = usuario_id

    async def dono(chat_id: str) -> Any:
        return estado["vinculos"].get(chat_id)

    async def enfileirar(job: str, **args: Any) -> None:
        estado["jobs"].append((job, args))

    monkeypatch.setattr(tg.ClienteTelegram, "enviar", enviar)
    monkeypatch.setattr(tg.ClienteTelegram, "digitando", digitando)
    monkeypatch.setattr(canais, "_vincular", vincular)
    monkeypatch.setattr(canais, "_dono_do_chat", dono)
    monkeypatch.setattr("workers.fila.enfileirar", enfileirar)
    aplicacao = criar_aplicacao()
    with TestClient(aplicacao) as cliente:
        aplicacao.state.redis = fakeredis.aioredis.FakeRedis()
        yield cliente, aplicacao, estado
    obter_configuracao.cache_clear()


def test_rota_do_webhook(api_telegram: Any) -> None:
    from app.core.seguranca import criar_token_acesso

    cliente, _, estado = api_telegram
    cabecalho = {tg.CABECALHO_SEGREDO: "segredo-do-webhook"}
    assert cliente.post("/v1/canais/telegram/webhook", json=_atualizacao()).status_code == 401
    assert (
        cliente.post(
            "/v1/canais/telegram/webhook", json=_atualizacao(), headers={tg.CABECALHO_SEGREDO: "x"}
        ).status_code
        == 401
    )
    resposta = cliente.post("/v1/canais/telegram/webhook", json=_atualizacao(), headers=cabecalho)
    assert resposta.json() == {"ok": True}
    assert estado["enviados"][-1][1].startswith("Oi! Para falar com a Sora")

    usuario = uuid4()
    token = criar_token_acesso({"sub": str(usuario)})
    vinculo = cliente.post(
        "/v1/canais/telegram/vinculo", headers={"Authorization": f"Bearer {token}"}
    )
    assert vinculo.status_code == 201
    codigo = vinculo.json()["codigo"]
    assert vinculo.json()["comando"] == f"/start {codigo}"
    cliente.post(
        "/v1/canais/telegram/webhook", json=_atualizacao(f"/start {codigo}"), headers=cabecalho
    )
    assert estado["vinculos"] == {"42": usuario}
    cliente.post(
        "/v1/canais/telegram/webhook", json=_atualizacao("/start ZZZZ9999"), headers=cabecalho
    )
    assert estado["enviados"][-1][1] == canais_api.TEXTO_CODIGO_INVALIDO
    cliente.post(
        "/v1/canais/telegram/webhook", json=_atualizacao("faz um resumo"), headers=cabecalho
    )
    job, args = estado["jobs"][-1]
    assert job == "responder_canal" and args["texto"] == "faz um resumo"
    assert args["id_job"] == "telegram:42:7" and args["usuario_id"] == str(usuario)


def test_rota_de_vinculo_exige_login(api_telegram: Any) -> None:
    cliente, _, _ = api_telegram
    assert cliente.post("/v1/canais/telegram/vinculo").status_code in (401, 403)


# ---------- voz ----------


def test_texto_falavel() -> None:
    texto = falavel(
        "## Plano\n- **Pesquisar** em [g1](https://g1.globo.com) 🎉\n"
        "```py\nprint(1)\n```\n| a | b |\n|---|---|\n| 1 | 2 |\nArquivo src/app/main.py"
    )
    assert "Plano." in texto and "Pesquisar em g1" in texto
    assert "(um bloco de código em Python)" in texto and "1, 2" in texto
    assert "main.py" in texto and "src/" not in texto and "🎉" not in texto and "**" not in texto
    assert falavel("🎉🎉") == ""
    assert falavel("veja https://a.com/x?y=1") == "veja um link"


def test_frases() -> None:
    partes = frases("Oi. Tudo bem? Hoje vamos montar a campanha da cafeteria. Ok.")
    assert partes == ["Oi. Tudo bem?", "Hoje vamos montar a campanha da cafeteria. Ok."]
    longa = frases("palavra, " * 100)
    assert all(len(p) <= 330 for p in longa) and len(longa) > 1
    assert frases("") == []


async def test_provedores_de_voz() -> None:
    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path.endswith("/audio/speech"):
            corpo = json.loads(pedido.content)
            assert corpo["voice"] == "alloy" and pedido.headers["authorization"] == "Bearer k"
            return httpx.Response(200, content=b"MP3")
        if pedido.url.path.endswith("/audio/transcriptions"):
            assert b"pt" in pedido.content
            return httpx.Response(200, json={"text": " olá "})
        if "/text-to-speech/" in pedido.url.path:
            assert pedido.url.path.endswith("/voz%2Fid") or "voz%2Fid" in str(pedido.url)
            return httpx.Response(401)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http:
        openai = VozOpenAI("k", cliente=http)
        assert (await openai.sintetizar("Oi")).conteudo == b"MP3"
        assert await openai.transcrever(b"...", "audio/webm") == "olá"
        with pytest.raises(ErroVoz, match="recusada"):
            await VozElevenLabs("k", cliente=http).sintetizar("Oi", "voz/id")
        with pytest.raises(ErroVoz, match="Nada"):
            await openai.sintetizar("  ")
    with pytest.raises(ErroVoz):
        obter_voz("outra", "k")
    with pytest.raises(ErroVoz):
        obter_voz("openai", "")


# ---------- navegador ----------


def test_snapshot_do_navegador() -> None:
    dados = {
        "url": "https://a.com",
        "titulo": "Loja",
        "texto": "x" * 9000,
        "total": 90,
        "elementos": [
            {"ref": "g1e1", "papel": "textbox", "nome": "Senha", "tag": "input", "valor": "••••"}
        ]
        + [
            {"ref": f"g1e{i}", "papel": "link", "nome": f"L{i}", "tag": "a", "valor": None}
            for i in range(2, 100)
        ],
    }
    snapshot = ler_snapshot(dados)
    assert len(snapshot.elementos) == 80 and len(snapshot.texto) == 8000
    texto = formatar_snapshot(snapshot)
    assert "- textbox 'Senha' [g1e1] valor='••••'" in texto and "mais 10 elementos" in texto


def test_refs_e_acoes_do_navegador() -> None:
    conferir_ref("g3e10", 3)
    for ruim, geracao in (("g2e1", 3), ("e1", 3), ("", 1)):
        with pytest.raises(ErroFerramenta):
            conferir_ref(ruim, geracao)
    validar_acao(AcaoNavegador(tipo="digitar", ref="g1e1", texto="oi"), 1)
    validar_acao(AcaoNavegador(tipo="tecla", tecla="Enter"), 1)
    for ruim in (
        AcaoNavegador(tipo="clicar"),
        AcaoNavegador(tipo="digitar", ref="g1e1"),
        AcaoNavegador(tipo="tecla", tecla="F12"),
    ):
        with pytest.raises(ErroFerramenta):
            validar_acao(ruim, 1)


# ---------- computador ----------


def test_argumentos_do_docker_travados() -> None:
    argv = SandboxDocker(imagem="python:3.12-slim").montar_argumentos(
        ExecutarComando(comando="echo $HOME; rm -rf /")
    )
    for trecho in ("--rm", "--read-only", "--cap-drop", "no-new-privileges", "65534:65534"):
        assert trecho in argv
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[-3:] == ["sh", "-c", "echo $HOME; rm -rf /"]
    com_rede = SandboxDocker().montar_argumentos(ExecutarComando(comando="pip", com_internet=True))
    assert com_rede[com_rede.index("--network") + 1] == "bridge"
    with pytest.raises(ValidationError):
        ExecutarComando(comando="x", prazo_segundos=301)


async def test_sandbox_falso_e_corte() -> None:
    falso = SandboxFalso({"ls": ResultadoComando(0, "a\nb", "")})
    resultado = await falso.executar(ExecutarComando(comando="ls"), [])
    assert "saída:\na\nb" in resultado.para_modelo() and falso.chamadas == ["ls"]
    assert "prazo estourado" in ResultadoComando(None, "", "", True).para_modelo()
    cortado = cortar("a" * 30_000, 1_000)
    assert len(cortado) < 1_100 and "cortados" in cortado
    with pytest.raises(ErroFerramenta, match="desligado"):
        obter_sandbox("nenhum", "x")


# ---------- gráficos ----------


async def test_gerar_grafico_png() -> None:
    barra = await gerar_grafico(
        GerarGrafico(
            tipo="barra",
            titulo="Vendas",
            series=[
                {"nome": "2025", "x": ["jan", "fev"], "y": [10, 12]},
                {"nome": "2026", "x": ["jan", "fev"], "y": [11, 15]},
            ],
        )
    )
    assert barra.startswith(b"\x89PNG")
    for tipo, series in (
        ("linha", [{"x": [1, 2, 3], "y": [1, 4, 9]}]),
        ("area", [{"x": ["a", "b"], "y": [1, 2]}]),
        ("dispersao", [{"x": [1, 2], "y": [3, 4]}]),
        ("histograma", [{"y": [1, 2, 2, 3, 3, 3]}]),
        ("pizza", [{"x": ["a", "b"], "y": [30, 70]}]),
    ):
        assert (await gerar_grafico(GerarGrafico(tipo=tipo, series=series))).startswith(b"\x89PNG")


def test_grafico_recusa_dados_incoerentes() -> None:
    for tipo, series in (
        ("barra", [{"x": ["a"], "y": [1, 2]}]),
        ("pizza", [{"x": ["a"], "y": [1]}, {"x": ["b"], "y": [2]}]),
        ("dispersao", [{"x": ["a"], "y": [1]}]),
        ("histograma", [{"x": [], "y": []}]),
        ("linha", [{"x": list(range(5001)), "y": [0] * 5001}]),
    ):
        with pytest.raises(ValidationError):
            GerarGrafico(tipo=tipo, series=series)


# ---------- busca sem chave ----------

HTML_DDG = """
<div class="result results_links web-result">
  <h2 class="result__title"><a class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.cafe.com.br%2Fsobre&amp;rut=x"
     >Café <b>Aurora</b></a></h2>
  <a class="result__snippet" href="#">O melhor <b>café</b> da cidade.</a>
</div>
<div class="result"><a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Anúncio</a></div>
<div class="result"><a class="result__a" href="javascript:alert(1)">X</a></div>
<div class="result"><a class="result__a" href="https://g1.globo.com/a">G1</a>
  <div class="result__snippet">Notícia</div></div>
"""


def test_ler_resultados_do_duckduckgo() -> None:
    assert desembrulhar("//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.com%2Fb") == "https://a.com/b"
    resultados = ler_resultados(HTML_DDG, 5)
    assert [r.url for r in resultados] == [
        "https://www.cafe.com.br/sobre",
        "https://g1.globo.com/a",
    ]
    assert resultados[0].titulo == "Café Aurora" and resultados[0].origem == "cafe.com.br"
    assert resultados[0].trecho == "O melhor café da cidade."
    assert len(ler_resultados(HTML_DDG, 1)) == 1


async def test_provedor_duckduckgo() -> None:
    def responder(pedido: httpx.Request) -> httpx.Response:
        assert b"q=caf" in pedido.content and b"kl=br-pt" in pedido.content
        return httpx.Response(200, text=HTML_DDG)

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http:
        assert len(await BuscaDuckDuckGo(cliente=http).buscar("café")) == 2

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(202))
    ) as http:
        with pytest.raises(ErroBusca, match="limitou"):
            await BuscaDuckDuckGo(cliente=http).buscar("café")
    assert isinstance(obter_provedor("duckduckgo", ambiente="desenvolvimento"), BuscaDuckDuckGo)
    with pytest.raises(BuscaProibidaEmProducao):
        obter_provedor("duckduckgo", ambiente="producao")


async def test_sessao_do_navegador_de_verdade() -> None:
    """Roda só onde o Chromium do Playwright está instalado (``playwright install chromium``)."""
    pytest.importorskip("playwright.async_api")
    from app.navegador.sessao import SessaoNavegador

    sessao = SessaoNavegador()
    try:
        await sessao.abrir_sessao()
    except Exception as erro:
        pytest.skip(f"Chromium indisponível: {type(erro).__name__}")
    try:
        await sessao._pagina.set_content(
            "<title>Loja</title><label for=s>Senha</label><input id=s type=password value=x>"
            "<button>Entrar</button><a href='https://a.com'>Ajuda</a>"
        )
        snapshot = await sessao.ler()
        papeis = [(e.papel, e.nome, e.valor) for e in snapshot.elementos]
        assert ("textbox", "Senha", "••••") in papeis and ("button", "Entrar", None) in papeis
        with pytest.raises(ErroFerramenta, match="antiga"):
            await sessao.agir([AcaoNavegador(tipo="clicar", ref="g0e1")])
        with pytest.raises(ErroFerramenta, match="recusado"):
            await sessao.abrir("http://127.0.0.1:1/")
    finally:
        await sessao.fechar()
