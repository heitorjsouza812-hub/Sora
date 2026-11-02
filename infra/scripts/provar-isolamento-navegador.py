"""Prova executada dentro do contêiner navegador; sai diferente de zero se a cerca falhar."""

from __future__ import annotations

import os
import socket
import urllib.error
import urllib.parse
import urllib.request

PROXY = os.environ.get("HTTP_PROXY", "http://proxy-egresso:3128")
PRIVADO = os.environ.get("SORA_TESTE_HOST_PRIVADO", "alvo-privado")


def http_falha(nome: str) -> None:
    try:
        urllib.request.urlopen(nome, timeout=8).read(1)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
        print(f"OK HTTP recusado: {nome}")
        return
    raise SystemExit(f"FALHA: HTTP alcançou {nome}")


def websocket_falha(host: str) -> None:
    proxy_host = urllib.parse.urlsplit(PROXY).hostname or "proxy-egresso"
    proxy_port = urllib.parse.urlsplit(PROXY).port or 3128
    with socket.create_connection((proxy_host, proxy_port), timeout=8) as conexao:
        pedido = (
            f"GET ws://{host}/ HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: c29yYS1wcm92YQ==\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        conexao.sendall(pedido.encode())
        status = conexao.recv(256).split(b"\r\n", 1)[0]
    if b" 403 " in status or b" 502 " in status:
        print(f"OK WebSocket recusado: {host} ({status.decode()})")
        return
    raise SystemExit(f"FALHA: WebSocket não foi recusado para {host}: {status!r}")


for destino in ("postgres", "redis", "169.254.169.254", PRIVADO):
    http_falha(f"http://{destino}/")
    websocket_falha(destino)

with urllib.request.urlopen("https://example.com/", timeout=15) as resposta:
    if resposta.status != 200:
        raise SystemExit(f"FALHA: site público respondeu {resposta.status}")
print("OK HTTPS público: https://example.com/")

# A ponte do CDP precisa reescrever o WebSocket mesmo com a barra final que o Playwright usa.
for caminho in ("/json/version", "/json/version/"):
    with urllib.request.urlopen(f"http://127.0.0.1:9223{caminho}", timeout=5) as resposta:
        ws = resposta.read().decode()
    if "ws://navegador:9223/devtools/" not in ws:
        raise SystemExit(f"FALHA: a ponte do CDP não reescreveu o WebSocket em {caminho}")
print("OK ponte CDP reescreve o WebSocket (com e sem barra final)")


def recusa_por_politica(alvo: str) -> None:
    """403 'Destino recusado' = o proxy resolveu, viu IP não público e recusou (não é falha de rede)."""
    for esquema in ("http", "ws"):
        with socket.create_connection(
            (urllib.parse.urlsplit(PROXY).hostname, urllib.parse.urlsplit(PROXY).port), timeout=8
        ) as conexao:
            extra = (
                "Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: c29yYS1wcm92YQ==\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                if esquema == "ws"
                else ""
            )
            conexao.sendall(
                f"GET {esquema}://{alvo}/ HTTP/1.1\r\nHost: {alvo}\r\n{extra}\r\n".encode()
            )
            status = conexao.recv(256).split(b"\r\n", 1)[0]
        if b" 403 " not in status:
            raise SystemExit(f"FALHA: {esquema}://{alvo} não foi recusado por política: {status!r}")
    print(f"OK recusa por política (IP resolvido): {alvo}")


# IP literal: CGNAT/Alibaba, RFC1918, loopback, link-local, IPv6 e IPv4 mapeado em IPv6.
for ip in (
    "100.100.100.200",
    "100.64.0.1",
    "10.0.0.5",
    "192.168.1.1",
    "172.16.0.1",
    "127.0.0.1",
    "169.254.169.254",
    "[::1]",
    "[fd00::1]",
    "[::ffff:10.0.0.5]",
    "[::ffff:100.100.100.200]",
):
    recusa_por_politica(ip)

# DNS rebinding: nomes que o proxy resolve para IP interno (extra_hosts do proxy-egresso).
for nome in ("rebind-privado.teste", "rebind-nuvem.teste", "rebind-cgnat.teste", "rebind-misto.teste"):
    recusa_por_politica(nome)
