"""Proxy HTTP/CONNECT mínimo: resolve uma vez, valida todos os IPs e conecta ao IP validado."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

LIMITE_CABECALHO = 64 * 1024
PRAZO = 20


def _publico(texto: str) -> bool:
    """Só IP globalmente roteável passa (recusa 100.64.0.0/10, metadados da Alibaba etc.)."""
    ip = ipaddress.ip_address(texto.split("%", 1)[0])
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None or ip.teredo is not None:
            return False
    return ip.is_global and not (ip.is_multicast or ip.is_loopback or ip.is_link_local)


async def _resolver(host: str, porta: int) -> list[tuple[int, str]]:
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, porta, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
        destinos = list(dict.fromkeys((familia, endereco[0]) for familia, _, _, _, endereco in infos))
    else:
        destinos = [(socket.AF_INET6 if literal.version == 6 else socket.AF_INET, str(literal))]
    if not destinos or any(not _publico(ip) for _, ip in destinos):
        raise PermissionError("destino privado ou especial")
    return destinos


async def _abrir(host: str, porta: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    ultimo: Exception | None = None
    for familia, ip in await _resolver(host, porta):
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(ip, porta, family=familia, server_hostname=None), PRAZO
            )
        except (OSError, asyncio.TimeoutError) as erro:
            ultimo = erro
    raise OSError("nenhum IP público respondeu") from ultimo


async def _copiar(leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
    try:
        while dados := await leitor.read(64 * 1024):
            escritor.write(dados)
            await escritor.drain()
    except (OSError, asyncio.CancelledError):
        pass
    finally:
        if not escritor.is_closing():
            escritor.close()


async def _responder(escritor: asyncio.StreamWriter, codigo: int, texto: str) -> None:
    corpo = (texto + "\n").encode()
    escritor.write(
        f"HTTP/1.1 {codigo} {texto}\r\nContent-Length: {len(corpo)}\r\n"
        "Connection: close\r\nContent-Type: text/plain\r\n\r\n".encode()
        + corpo
    )
    await escritor.drain()


def _destino(metodo: str, alvo: str, cabecalhos: list[bytes]) -> tuple[str, int, bytes]:
    if metodo == "CONNECT":
        host, separador, porta = alvo.rpartition(":")
        if not separador:
            raise ValueError("CONNECT sem porta")
        return host.strip("[]"), int(porta), b""
    url = urlsplit(alvo)
    if url.scheme not in {"http", "ws"} or not url.hostname:
        raise ValueError("somente HTTP, HTTPS, WS e WSS")
    porta = url.port or 80
    caminho = url.path or "/"
    if url.query:
        caminho += "?" + url.query
    primeira = f"{metodo} {caminho} HTTP/1.1\r\n".encode()
    filtrados = [linha for linha in cabecalhos if not linha.lower().startswith(b"proxy-")]
    return url.hostname, porta, primeira + b"\r\n".join(filtrados) + b"\r\n\r\n"


async def _cliente(leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
    remoto: asyncio.StreamWriter | None = None
    try:
        bruto = await asyncio.wait_for(leitor.readuntil(b"\r\n\r\n"), PRAZO)
        if len(bruto) > LIMITE_CABECALHO:
            raise ValueError("cabeçalho grande")
        linhas = bruto[:-4].split(b"\r\n")
        metodo_b, alvo_b, _ = linhas[0].split(b" ", 2)
        metodo, alvo = metodo_b.decode("ascii").upper(), alvo_b.decode("ascii")
        host, porta, pedido = _destino(metodo, alvo, linhas[1:])
        remoto_leitor, remoto = await _abrir(host, porta)
        if metodo == "CONNECT":
            escritor.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        else:
            remoto.write(pedido)
        await escritor.drain()
        if remoto is not None:
            await asyncio.gather(_copiar(leitor, remoto), _copiar(remoto_leitor, escritor))
    except PermissionError:
        await _responder(escritor, 403, "Destino recusado")
    except (ValueError, UnicodeError, asyncio.IncompleteReadError):
        await _responder(escritor, 400, "Pedido inválido")
    except (OSError, asyncio.TimeoutError):
        await _responder(escritor, 502, "Destino indisponível")
    finally:
        if remoto is not None and not remoto.is_closing():
            remoto.close()
        if not escritor.is_closing():
            escritor.close()


async def _principal() -> None:
    servidor = await asyncio.start_server(_cliente, "0.0.0.0", 3128)
    async with servidor:
        await servidor.serve_forever()


if __name__ == "__main__":
    asyncio.run(_principal())
