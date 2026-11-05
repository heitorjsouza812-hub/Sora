"""Servidor MCP de verdade (streamable HTTP) para os testes de conectores.

Uso: ``python servidor_mcp.py PORTA ARQUIVO_DE_CHAMADAS``. Cada chamada de ferramenta é anotada
no arquivo, para o teste provar o que o agente chamou (e o que não chamou). Exige o cabeçalho
``Authorization: Bearer segredo-do-teste``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP

PORTA = int(sys.argv[1])
CHAMADAS = Path(sys.argv[2])

mcp = FastMCP("clima", host="127.0.0.1", port=PORTA)


def anotar(texto: str) -> None:
    with CHAMADAS.open("a", encoding="utf-8") as arquivo:
        arquivo.write(texto + "\n")


@mcp.tool()
def buscar_clima(cidade: str) -> str:
    """Busca o clima de uma cidade (só leitura)."""
    anotar(f"buscar_clima:{cidade}")
    return f"Sol em {cidade}, 29 graus"


@mcp.tool()
def enviar_email(para: str, texto: str) -> str:
    """Envia um e-mail (escreve fora da Sora)."""
    anotar(f"enviar_email:{para}")
    return "enviado"


class ExigeToken:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            cabecalhos = dict(scope["headers"])
            if cabecalhos.get(b"authorization") != b"Bearer segredo-do-teste":
                await send({"type": "http.response.start", "status": 401, "headers": []})
                await send({"type": "http.response.body", "body": b"nao autorizado"})
                return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    uvicorn.run(
        ExigeToken(mcp.streamable_http_app()), host="127.0.0.1", port=PORTA, log_level="warning"
    )
