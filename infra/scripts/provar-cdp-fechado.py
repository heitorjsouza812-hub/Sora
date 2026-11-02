"""Roda no contêiner proxy-egresso: ele não pode falar com o CDP (nem a ponte, nem o Chromium)."""

import socket

PEDIDO = b"GET /json/version HTTP/1.1\r\nHost: navegador\r\n\r\n"

for porta in (9222, 9223):
    try:
        with socket.create_connection(("navegador", porta), timeout=4) as conexao:
            conexao.sendall(PEDIDO)
            dados = conexao.recv(200)
    except OSError as erro:
        print(f"OK CDP porta {porta}: proxy sem acesso ({type(erro).__name__})")
        continue
    if dados:
        raise SystemExit(f"FALHA: o proxy alcançou o CDP na porta {porta}: {dados[:60]!r}")
    print(f"OK CDP porta {porta}: conexão fechada para o proxy")
