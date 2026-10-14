"""``app/busca/ler_pagina.py``: SSRF, limites e extração (especificação §8.1 e §8.5).

Sem rede: o DNS é um dicionário e o HTTP é ``httpx.MockTransport``.
"""

import asyncio
import ipaddress

import fakeredis
import httpcore
import httpx
import pytest

from app.busca import ler_pagina as lp
from app.busca.ler_pagina import (
    BackendSeguro,
    EnderecoBloqueado,
    ErroLeitura,
    extrair_texto,
    ip_bloqueado,
    ler_pagina,
    validar_destino,
)

HTML = (
    b"<html><head><title>Caf\xc3\xa9 gelado</title></head><body><nav>menu</nav><article><p>"
    + "O café gelado virou o pedido mais comum nas tardes de verão. ".encode() * 10
    + b"</p></article><footer>rodape</footer></body></html>"
)

DNS = {
    "exemplo.com.br": ["93.184.216.34"],
    "duplo.exemplo": ["93.184.216.34", "10.0.0.5"],
    "interno.exemplo": ["192.168.1.10"],
    "localhost": ["127.0.0.1"],
}


async def resolver_falso(host: str, porta: int) -> list[str]:
    return DNS.get(host, [])


def cliente_com(manipulador) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(transport=httpx.MockTransport(manipulador), follow_redirects=False)


def html_ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=HTML, headers={"content-type": "text/html; charset=utf-8"})


# ---------- tabela de IPs ----------


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "127.255.255.254",
        "10.1.2.3",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.0.1",
        "169.254.169.254",  # metadados AWS/GCP/Azure
        "100.100.100.200",  # metadados Alibaba (CGNAT)
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "255.255.255.255",
        "192.0.2.10",  # documentação
        "198.18.0.1",  # benchmark
        "::1",
        "::",
        "fe80::1",
        "fd00:ec2::254",  # metadados AWS IPv6
        "fc00::1",
        "::ffff:127.0.0.1",  # IPv4 mapeado
        "::ffff:169.254.169.254",
        "2002:7f00:1::1",  # 6to4 de 127.0.0.1
        "64:ff9b::a00:1",  # NAT64 de 10.0.0.1
        "2001:0:4136:e378:8000:63bf:3fff:fdd2",  # Teredo
        "ff02::1",
    ],
)
def test_ip_interno_e_bloqueado(ip: str) -> None:
    assert ip_bloqueado(ipaddress.ip_address(ip))


@pytest.mark.parametrize(
    "ip", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111", "64:ff9b::808:808"]
)
def test_ip_publico_passa(ip: str) -> None:
    assert not ip_bloqueado(ipaddress.ip_address(ip))


# ---------- validar_destino ----------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]:8080/",
        "http://[::ffff:10.0.0.1]/",
        "http://localhost:6379/",
        "http://interno.exemplo/",
        "http://duplo.exemplo/",  # basta um IP interno
        "file:///etc/passwd",
        "gopher://exemplo.com.br/",
        "http://usuario:senha@exemplo.com.br/",
    ],
)
async def test_destino_bloqueado(url: str) -> None:
    with pytest.raises(EnderecoBloqueado):
        await validar_destino(url, resolver_falso)


async def test_destino_publico_passa() -> None:
    await validar_destino("https://exemplo.com.br/pagina", resolver_falso)


async def test_dominio_sem_ip_e_erro() -> None:
    with pytest.raises(ErroLeitura):
        await validar_destino("https://nao-existe.exemplo/", resolver_falso)


# ---------- leitura ----------


async def test_le_html_e_tira_menu_e_rodape() -> None:
    async with cliente_com(html_ok) as cliente:
        pagina = await ler_pagina(
            "https://exemplo.com.br/cafe", cliente=cliente, resolver=resolver_falso
        )
    assert pagina.titulo == "Café gelado"
    assert "café gelado virou o pedido" in pagina.texto
    assert "menu" not in pagina.texto and "rodape" not in pagina.texto
    assert pagina.tipo == "text/html"


async def test_url_interna_nem_chega_a_ser_baixada() -> None:
    chamadas: list[httpx.Request] = []

    def manipulador(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        return html_ok(requisicao)

    async with cliente_com(manipulador) as cliente:
        with pytest.raises(EnderecoBloqueado):
            await ler_pagina("http://127.0.0.1/", cliente=cliente, resolver=resolver_falso)
    assert chamadas == []


async def test_redirecionamento_para_rede_interna_e_bloqueado() -> None:
    chamadas: list[str] = []

    def manipulador(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(str(requisicao.url))
        if requisicao.url.host == "exemplo.com.br":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})
        return html_ok(requisicao)

    async with cliente_com(manipulador) as cliente:
        with pytest.raises(EnderecoBloqueado):
            await ler_pagina("https://exemplo.com.br/", cliente=cliente, resolver=resolver_falso)
    assert chamadas == ["https://exemplo.com.br/"]


async def test_redirecionamento_relativo_e_seguido() -> None:
    def manipulador(requisicao: httpx.Request) -> httpx.Response:
        if requisicao.url.path == "/antiga":
            return httpx.Response(301, headers={"location": "/nova"})
        return html_ok(requisicao)

    async with cliente_com(manipulador) as cliente:
        pagina = await ler_pagina(
            "https://exemplo.com.br/antiga", cliente=cliente, resolver=resolver_falso
        )
    assert pagina.url_final == "https://exemplo.com.br/nova"


async def test_mais_de_5_redirecionamentos_e_erro() -> None:
    def manipulador(requisicao: httpx.Request) -> httpx.Response:
        n = int(requisicao.url.params.get("n", "0"))
        return httpx.Response(302, headers={"location": f"/?n={n + 1}"})

    async with cliente_com(manipulador) as cliente:
        with pytest.raises(ErroLeitura, match="Redirecionamentos demais"):
            await ler_pagina("https://exemplo.com.br/", cliente=cliente, resolver=resolver_falso)


async def test_conteudo_maior_que_5_mb_e_cortado() -> None:
    grande = b"a" * (lp.MAX_BYTES + 1)

    def manipulador(_: httpx.Request) -> httpx.Response:
        # sem content-length: o limite vale durante o download
        return httpx.Response(
            200, stream=httpx.ByteStream(grande), headers={"content-type": "text/plain"}
        )

    async with cliente_com(manipulador) as cliente:
        with pytest.raises(ErroLeitura, match="5 MB"):
            await ler_pagina("https://exemplo.com.br/", cliente=cliente, resolver=resolver_falso)


async def test_content_length_grande_e_recusado_antes() -> None:
    def manipulador(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x",
            headers={"content-type": "text/plain", "content-length": str(lp.MAX_BYTES + 1)},
        )

    async with cliente_com(manipulador) as cliente:
        with pytest.raises(ErroLeitura, match="5 MB"):
            await ler_pagina("https://exemplo.com.br/", cliente=cliente, resolver=resolver_falso)


async def test_prazo_estourado_vira_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lp, "PRAZO_SEGUNDOS", 0.05)

    async def manipulador(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200)

    async with cliente_com(manipulador) as cliente:
        with pytest.raises(ErroLeitura, match="demorou"):
            await ler_pagina("https://exemplo.com.br/", cliente=cliente, resolver=resolver_falso)


async def test_erro_http_vira_erro_de_leitura() -> None:
    async with cliente_com(lambda _: httpx.Response(404)) as cliente:
        with pytest.raises(ErroLeitura, match="404"):
            await ler_pagina("https://exemplo.com.br/", cliente=cliente, resolver=resolver_falso)


async def test_cache_de_24_horas_evita_novo_download() -> None:
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    chamadas = 0

    def manipulador(requisicao: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        return html_ok(requisicao)

    url = "https://exemplo.com.br/cafe"
    async with cliente_com(manipulador) as cliente:
        primeira = await ler_pagina(url, redis=redis, cliente=cliente, resolver=resolver_falso)
        segunda = await ler_pagina(url, redis=redis, cliente=cliente, resolver=resolver_falso)
    assert primeira == segunda
    assert chamadas == 1
    assert 0 < await redis.ttl(lp.chave_cache(url)) <= lp.CACHE_SEGUNDOS
    await redis.aclose()


# ---------- camada de rede (DNS rebinding) ----------


async def test_backend_seguro_conecta_no_ip_conferido() -> None:
    conectados: list[str] = []

    class Interno(httpcore.AsyncMockBackend):
        async def connect_tcp(  # type: ignore[no-untyped-def]
            self,
            host,
            port,
            timeout=None,  # noqa: ASYNC109 (assinatura do httpcore)
            local_address=None,
            socket_options=None,
        ):
            conectados.append(host)
            return await super().connect_tcp(host, port, timeout, local_address, socket_options)

    backend = BackendSeguro(resolver_falso, interno=Interno([]))
    await backend.connect_tcp("exemplo.com.br", 443)
    assert conectados == ["93.184.216.34"]


async def test_backend_seguro_recusa_quando_o_dns_muda_para_interno() -> None:
    respostas = iter([["93.184.216.34"], ["127.0.0.1"]])

    async def dns_que_muda(host: str, porta: int) -> list[str]:
        return next(respostas)

    await validar_destino("https://rebind.exemplo/", dns_que_muda)  # 1ª resolução: pública
    backend = BackendSeguro(dns_que_muda, interno=httpcore.AsyncMockBackend([]))
    with pytest.raises(EnderecoBloqueado):
        await backend.connect_tcp("rebind.exemplo", 443)  # 2ª resolução: interna


async def test_backend_seguro_recusa_socket_unix() -> None:
    with pytest.raises(EnderecoBloqueado):
        await BackendSeguro(resolver_falso).connect_unix_socket("/var/run/docker.sock")


def test_cliente_padrao_usa_o_backend_seguro_e_ignora_proxy() -> None:
    cliente = lp.criar_cliente(resolver_falso)
    assert isinstance(cliente._transport._pool._network_backend, BackendSeguro)  # type: ignore[attr-defined]
    assert cliente.trust_env is False
    assert cliente.follow_redirects is False


# ---------- extração ----------


def _pdf_com_texto(texto: str) -> bytes:
    conteudo = f"BT /F1 12 Tf 72 720 Td ({texto}) Tj ET".encode()
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(conteudo)).encode() + b" >>\nstream\n" + conteudo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Title (Relatorio) >>",
    ]
    saida = bytearray(b"%PDF-1.4\n")
    posicoes = []
    for numero, corpo in enumerate(objetos, start=1):
        posicoes.append(len(saida))
        saida += f"{numero} 0 obj\n".encode() + corpo + b"\nendobj\n"
    xref = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for posicao in posicoes:
        saida += f"{posicao:010d} 00000 n \n".encode()
    saida += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R /Info 6 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(saida)


def test_extrai_pdf() -> None:
    titulo, texto = extrair_texto(_pdf_com_texto("Vendas de cafe em 2026"), "application/pdf", "")
    assert titulo == "Relatorio"
    assert "Vendas de cafe em 2026" in texto


def test_extrai_texto_puro() -> None:
    assert extrair_texto("olá\n".encode(), "text/plain", "") == (None, "olá")


@pytest.mark.parametrize("tipo", ["image/png", "application/zip", "application/octet-stream"])
def test_tipo_nao_suportado(tipo: str) -> None:
    with pytest.raises(ErroLeitura, match="Não leio"):
        extrair_texto(b"\x89PNG", tipo, "")


def test_pagina_sem_texto_e_erro() -> None:
    with pytest.raises(ErroLeitura, match="texto"):
        extrair_texto(b"<html><body></body></html>", "text/html", "https://exemplo.com.br/")


def test_pdf_quebrado_e_erro() -> None:
    with pytest.raises(ErroLeitura):
        extrair_texto(b"%PDF-1.4 lixo", "application/pdf", "")
