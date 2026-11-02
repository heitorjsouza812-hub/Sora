"""Expõe o CDP preso ao loopback do Chrome para a rede de controle, reescrevendo o WS."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os

ORIGEM = ("127.0.0.1", 9222)
CAMINHOS_COM_WS = {"/json", "/json/list", "/json/version", "/json/new", "/json/protocol"}
"""Rotas do CDP cujo JSON traz ``webSocketDebuggerUrl``."""
REDE_PERMITIDA = os.environ.get("PONTE_REDE_PERMITIDA", "")
"""CIDR da rede de controle. Só quem vem dela fala com a ponte (o proxy, na rede isolada, não)."""


def cliente_permitido(ip: str, cidr: str = REDE_PERMITIDA) -> bool:
    if not cidr:
        return False  # sem rede configurada, ninguém entra (falha fechada)
    # loopback: o healthcheck do próprio contêiner
    try:
        endereco = ipaddress.ip_address(ip)
        return endereco.is_loopback or endereco in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def reescrever_ws(valor: object) -> object:
    """Troca o host do ``webSocketDebuggerUrl`` (objeto ou lista de objetos) pelo da ponte."""
    if isinstance(valor, list):
        return [reescrever_ws(item) for item in valor]
    if isinstance(valor, dict):
        for chave in ("webSocketDebuggerUrl", "devtoolsFrontendUrl"):
            if isinstance(valor.get(chave), str) and "/devtools/" in valor[chave]:
                caminho = valor[chave].split("/devtools/", 1)[1]
                if chave == "webSocketDebuggerUrl":
                    valor[chave] = f"ws://navegador:9223/devtools/{caminho}"
                else:
                    del valor[chave]  # o front-end do DevTools aponta para o CDP cru
    return valor


def caminho_do_pedido(linha: bytes) -> str:
    return linha.split(b" ", 2)[1].split(b"?", 1)[0].decode().rstrip("/") or "/"


async def copiar(leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
    try:
        while dados := await leitor.read(64 * 1024):
            escritor.write(dados)
            await escritor.drain()
    except (OSError, asyncio.CancelledError):
        pass
    finally:
        if not escritor.is_closing():
            escritor.close()


async def cliente(leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
    origem: asyncio.StreamWriter | None = None
    par = escritor.get_extra_info("peername")
    if not par or not cliente_permitido(par[0]):
        escritor.close()
        return
    try:
        pedido = await leitor.readuntil(b"\r\n\r\n")
        linhas = pedido[:-4].split(b"\r\n")
        cabecalhos = []
        upgrade = False
        for linha in linhas[1:]:
            if linha.lower().startswith(b"host:"):
                linha = b"Host: 127.0.0.1:9222"
            if linha.lower().startswith(b"upgrade: websocket"):
                upgrade = True
            cabecalhos.append(linha)
        origem_leitor, origem = await asyncio.open_connection(*ORIGEM)
        origem.write(linhas[0] + b"\r\n" + b"\r\n".join(cabecalhos) + b"\r\n\r\n")
        await origem.drain()
        if upgrade:
            await asyncio.gather(copiar(leitor, origem), copiar(origem_leitor, escritor))
            return
        cabecalho = (await origem_leitor.readuntil(b"\r\n\r\n"))[:-4]
        tamanho = next(
            (
                int(linha.split(b":", 1)[1].strip())
                for linha in cabecalho.split(b"\r\n")
                if linha.lower().startswith(b"content-length:")
            ),
            0,
        )
        corpo = await origem_leitor.readexactly(tamanho) if tamanho else b""
        # O Playwright pede "/json/version/" (com barra): compara sem a barra final.
        if caminho_do_pedido(linhas[0]) in CAMINHOS_COM_WS:
            dados = reescrever_ws(json.loads(corpo))
            corpo = json.dumps(dados).encode()
            cabecalho = b"\r\n".join(
                linha
                for linha in cabecalho.split(b"\r\n")
                if not linha.lower().startswith(b"content-length:")
            )
            cabecalho += f"\r\nContent-Length: {len(corpo)}".encode()
        escritor.write(cabecalho + b"\r\n\r\n" + corpo)
        await escritor.drain()
    except (OSError, asyncio.IncompleteReadError, KeyError, ValueError, json.JSONDecodeError):
        escritor.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        await escritor.drain()
    finally:
        if origem is not None and not origem.is_closing():
            origem.close()
        if not escritor.is_closing():
            escritor.close()


async def principal() -> None:
    for _ in range(100):
        try:
            leitor, escritor = await asyncio.open_connection(*ORIGEM)
        except OSError:
            await asyncio.sleep(0.1)
        else:
            escritor.close()
            await escritor.wait_closed()
            break
    servidor = await asyncio.start_server(cliente, "0.0.0.0", 9223)
    async with servidor:
        await servidor.serve_forever()


if __name__ == "__main__":
    asyncio.run(principal())
