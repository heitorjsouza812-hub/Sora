"""Operações de teste pelas interfaces públicas e consultas SQL."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from httpx import AsyncClient
from sqlalchemy import text


async def sql(mundo, consulta: str, **parametros):
    async with mundo.fabrica.begin() as sessao:
        resultado = await sessao.execute(text(consulta), parametros)
        return resultado.mappings().all() if resultado.returns_rows else None


async def entrar(cliente: AsyncClient, mundo, email: str) -> dict[str, str]:
    senha = "Senha-local-dos-testes-42!"
    cadastro = await cliente.post(
        "/v1/auth/cadastrar",
        json={"nome": "Ana", "email": email, "senha": senha, "convite": "FASE-B"},
    )
    assert cadastro.status_code == 201, cadastro.text
    login = await cliente.post("/v1/auth/entrar", json={"email": email, "senha": senha})
    assert login.status_code == 200, login.text
    await sql(
        mundo,
        """
        with conexao as (
            insert into provedores (usuario_id, tipo, validado_em)
            select id, 'groq', now() from usuarios where email = :email
            returning id
        )
        insert into modelos_disponiveis
            (provedor_id, modelo, nivel, capacidades, contexto, velocidade_tps)
        select id, 'groq/openai/gpt-oss-20b', 'N1', '{ferramentas,json}', 131072, 100
        from conexao
        """,
        email=email,
    )
    return {"Authorization": f"Bearer {login.json()['token_acesso']}"}


async def criar_conversa(cliente: AsyncClient, pedido: str) -> str:
    resposta = await cliente.post("/v1/conversas", json={"texto": pedido})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


@dataclass(frozen=True)
class Evento:
    id: str
    nome: str
    dados: dict


async def eventos(
    cliente: AsyncClient, conversa_id: str, *, cursor: str = "0-0"
) -> AsyncIterator[Evento]:
    async with cliente.stream(
        "GET", f"/v1/conversas/{conversa_id}/eventos", headers={"Last-Event-ID": cursor}
    ) as resposta:
        assert resposta.status_code == 200
        campos = {}
        async for linha in resposta.aiter_lines():
            if not linha:
                if "event" in campos:
                    yield Evento(campos["id"], campos["event"], json.loads(campos["data"]))
                campos.clear()
            elif not linha.startswith(":"):
                nome, _, valor = linha.partition(":")
                campos[nome] = valor.lstrip()


async def ler_ate(cliente: AsyncClient, conversa_id: str, ate, *, cursor: str = "0-0"):
    vistos = []
    fluxo = eventos(cliente, conversa_id, cursor=cursor)
    try:
        async with asyncio.timeout(30):
            async for evento in fluxo:
                vistos.append(evento)
                if ate(evento):
                    return vistos
    finally:
        await fluxo.aclose()
    raise AssertionError(f"SSE encerrou antes do evento esperado: {vistos}")
