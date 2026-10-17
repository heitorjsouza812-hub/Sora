"""Servidores MCP do usuário: validação, conexão segura e embrulho das ferramentas.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``remote-mcp.ts``,
``mcp-transport.ts``, ``mcp-origin-fallback.ts`` e ``connector-safety.ts``.

Regras:

- só ``https`` com host público (a mesma proteção SSRF do ``ler_pagina``); ``http`` só para
  ``localhost`` em desenvolvimento;
- os cabeçalhos (tokens) ficam cifrados em ``conectores.cabecalhos_cifrados`` e só são
  decifrados pelo worker na hora de conectar;
- toda ferramenta embrulhada: prazo de 2 minutos, erro sem segredo, resultado dentro da cerca
  ``<dado_externo>`` e nome ``mcp__<servidor>__<ferramenta>``;
- mais de 20 ferramentas vão pelo catálogo preguiçoso.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, Field, field_validator

from app.agentes.prompts import cercar
from app.busca.ler_pagina import (
    EnderecoBloqueado,
    ErroLeitura,
    transporte_seguro,
    validar_destino,
    validar_url,
)
from app.conectores.nomes import nome_conector, nomes_unicos, slug_servidor
from app.core.redacao import sanitizar_erro
from app.ferramentas.base import (
    LIMITE_RESULTADO_CARACTERES,
    PRAZO_FERRAMENTA_SEGUNDOS,
    ErroFerramenta,
)
from app.ferramentas.catalogo_preguicoso import AntesDeExecutar, montar_catalogo

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

MAX_SERVIDORES = 10
MAX_CABECALHOS = 10
PRAZO_CONEXAO_SEGUNDOS = 15
_CABECALHOS_PROIBIDOS = {"host", "content-length", "transfer-encoding", "connection", "cookie"}

DESCRICAO_ADICIONAR = (
    "Conecta um servidor MCP remoto que o usuário pediu, com o endereço e os cabeçalhos que ele "
    "passou. Abre um cartão de aprovação; diga ao usuário para aprovar no cartão."
)


class AdicionarServidorMCP(BaseModel):
    """Conecta um servidor MCP remoto (pede aprovação)."""

    nome: str = Field(min_length=1, max_length=40)
    url: str = Field(min_length=8, max_length=2_000)
    cabecalhos: dict[str, str] = Field(default_factory=dict, description="Ex.: Authorization.")

    @field_validator("cabecalhos")
    @classmethod
    def _cabecalhos_validos(cls, valor: dict[str, str]) -> dict[str, str]:
        if len(valor) > MAX_CABECALHOS:
            raise ValueError(f"no máximo {MAX_CABECALHOS} cabeçalhos")
        for chave, conteudo in valor.items():
            if chave.strip().lower() in _CABECALHOS_PROIBIDOS:
                raise ValueError(f"cabeçalho não permitido: {chave}")
            if "\n" in chave or "\r" in chave or "\n" in conteudo or "\r" in conteudo:
                raise ValueError("cabeçalho com quebra de linha")
        return valor


class ServidorMCP(BaseModel):
    """Um servidor já aprovado, com os cabeçalhos decifrados (só existe dentro do worker)."""

    nome: str
    url: str
    cabecalhos: dict[str, str] = Field(default_factory=dict)


def _local(alvo: httpx.URL) -> bool:
    return alvo.host in {"localhost", "127.0.0.1", "::1"}


async def validar_servidor(url: str, *, ambiente_local: bool = False, resolver: Any = None) -> str:
    """Confere o endereço do servidor. Devolve a URL normalizada ou levanta ``ErroFerramenta``."""
    try:
        alvo = validar_url(url)
    except (EnderecoBloqueado, ErroLeitura) as erro:
        raise ErroFerramenta(f"Endereço do servidor recusado: {erro}") from erro
    if ambiente_local and alvo.scheme == "http" and _local(alvo):
        return str(alvo)
    if alvo.scheme != "https":
        raise ErroFerramenta("O servidor MCP precisa usar https.")
    try:
        if resolver is None:
            await validar_destino(alvo)
        else:
            await validar_destino(alvo, resolver)
    except (EnderecoBloqueado, ErroLeitura) as erro:
        raise ErroFerramenta(f"Endereço do servidor recusado: {erro}") from erro
    return str(alvo)


def fabrica_cliente_seguro(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """``McpHttpClientFactory`` com o transporte que só conecta em IP público."""
    return httpx.AsyncClient(
        transport=transporte_seguro(),
        headers=headers,
        timeout=timeout or httpx.Timeout(PRAZO_CONEXAO_SEGUNDOS, read=300),
        auth=auth,
        follow_redirects=False,
        trust_env=False,
    )


def montar_conexoes(
    servidores: Sequence[ServidorMCP], *, ambiente_local: bool = False
) -> dict[str, Any]:
    """Conexões para o ``MultiServerMCPClient`` (transporte streamable HTTP)."""
    if len(servidores) > MAX_SERVIDORES:
        raise ErroFerramenta(f"No máximo {MAX_SERVIDORES} servidores MCP por usuário.")
    conexoes: dict[str, Any] = {}
    for servidor in servidores:
        conexao: dict[str, Any] = {
            "transport": "streamable_http",
            "url": servidor.url,
            "headers": dict(servidor.cabecalhos) or None,
            "timeout": PRAZO_CONEXAO_SEGUNDOS,
        }
        if not (ambiente_local and _local(httpx.URL(servidor.url))):
            conexao["httpx_client_factory"] = fabrica_cliente_seguro
        conexoes[slug_servidor(servidor.nome)] = conexao
    return conexoes


def _texto_do_resultado(resultado: Any) -> str:
    if isinstance(resultado, tuple) and len(resultado) == 2:
        resultado = resultado[0]  # (conteúdo, artefato) do adaptador
    if isinstance(resultado, str):
        return resultado
    if isinstance(resultado, list):
        partes = []
        for item in resultado:
            if isinstance(item, dict) and item.get("type") == "text":
                partes.append(str(item.get("text", "")))
            else:
                partes.append(json.dumps(item, ensure_ascii=False, default=str))
        return "\n".join(partes)
    return json.dumps(resultado, ensure_ascii=False, default=str)


def embrulhar(
    ferramenta: BaseTool, servidor: str, nome_visivel: str, segredos: Sequence[str] = ()
) -> BaseTool:
    """Ferramenta nova com nome seguro, prazo, erro sem segredo e resultado cercado."""
    from langchain_core.tools import StructuredTool

    metadata = dict(getattr(ferramenta, "metadata", None) or {})
    metadata.update({"servidor": servidor, "grupo": servidor, "nome_original": ferramenta.name})

    async def _rodar(**argumentos: Any) -> str:
        try:
            resultado = await asyncio.wait_for(
                ferramenta.ainvoke(argumentos), PRAZO_FERRAMENTA_SEGUNDOS
            )
        except TimeoutError as erro:
            raise ErroFerramenta(f"O conector {servidor} demorou demais.") from erro
        except ErroFerramenta:
            raise
        except Exception as erro:
            raise ErroFerramenta(
                f"O conector {servidor} falhou: {sanitizar_erro(erro, segredos)}"
            ) from erro
        texto = _texto_do_resultado(resultado)
        if len(texto) > LIMITE_RESULTADO_CARACTERES:
            texto = texto[:LIMITE_RESULTADO_CARACTERES] + "\n[… resultado cortado]"
        return cercar(texto, f"conector:{servidor}")

    return StructuredTool.from_function(
        coroutine=_rodar,
        name=nome_visivel,
        description=(ferramenta.description or "")[:1_000],
        args_schema=ferramenta.args_schema,
        metadata=metadata,
    )


async def carregar_ferramentas(
    servidores: Sequence[ServidorMCP],
    *,
    ambiente_local: bool = False,
    antes_de_executar: AntesDeExecutar | None = None,
    cliente: Any = None,
) -> list[BaseTool]:
    """Liga nos servidores, embrulha as ferramentas e aplica o catálogo preguiçoso.

    Servidor que falha não derruba os outros: as ferramentas dele só não aparecem.
    ``cliente`` permite injetar um ``MultiServerMCPClient`` falso nos testes.
    """
    if not servidores:
        return []
    if cliente is None:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        cliente = MultiServerMCPClient(montar_conexoes(servidores, ambiente_local=ambiente_local))
    segredos = [v for s in servidores for v in s.cabecalhos.values()]
    brutas: list[tuple[str, BaseTool]] = []
    for servidor in servidores:
        slug = slug_servidor(servidor.nome)
        try:
            ferramentas = await cliente.get_tools(server_name=slug)
        except Exception:
            continue
        brutas.extend((slug, f) for f in ferramentas)
    visiveis = nomes_unicos([nome_conector(slug, f.name) for slug, f in brutas])
    embrulhadas = [
        embrulhar(f, slug, nome, segredos) for (slug, f), nome in zip(brutas, visiveis, strict=True)
    ]
    return montar_catalogo(embrulhadas, antes_de_executar=antes_de_executar)
