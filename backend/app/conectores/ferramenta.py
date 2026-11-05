"""Função da ferramenta ``adicionar_servidor_mcp`` (roda depois do cartão de aprovação) e
leitura dos conectores do usuário para o worker."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conectores.servidores import (
    MAX_SERVIDORES,
    AdicionarServidorMCP,
    ServidorMCP,
    validar_servidor,
)
from app.core.config import obter_configuracao
from app.core.seguranca import cifrar_segredo, decifrar_segredo
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.infra import abrir_sessao
from app.modelos.tabelas import Conector

PROVEDOR_CIFRA = "conector"


def cifrar_cabecalhos(usuario_id: UUID, cabecalhos: dict[str, str]) -> bytes | None:
    if not cabecalhos:
        return None
    return cifrar_segredo(
        json.dumps(cabecalhos, ensure_ascii=False), usuario_id=usuario_id, provedor=PROVEDOR_CIFRA
    )


def decifrar_cabecalhos(conector: Conector) -> dict[str, str]:
    if not conector.cabecalhos_cifrados:
        return {}
    texto = decifrar_segredo(
        conector.cabecalhos_cifrados, usuario_id=conector.usuario_id, provedor=PROVEDOR_CIFRA
    )
    return {str(k): str(v) for k, v in json.loads(texto).items()}


def ambiente_local() -> bool:
    return not obter_configuracao().producao


async def criar_conector(
    sessao: AsyncSession, usuario_id: UUID, nome: str, url: str, cabecalhos: dict[str, str]
) -> Conector:
    """Valida o endereço (https público) e grava com os cabeçalhos cifrados."""
    url_ok = await validar_servidor(url, ambiente_local=ambiente_local())
    existentes = (
        await sessao.scalars(select(Conector).where(Conector.usuario_id == usuario_id))
    ).all()
    if len(existentes) >= MAX_SERVIDORES:
        raise ErroFerramenta(f"No máximo {MAX_SERVIDORES} servidores MCP por usuário.")
    if any(c.nome.lower() == nome.strip().lower() for c in existentes):
        raise ErroFerramenta("Já existe um conector com esse nome.")
    conector = Conector(
        usuario_id=usuario_id,
        nome=nome.strip(),
        url=url_ok,
        cabecalhos_cifrados=cifrar_cabecalhos(usuario_id, cabecalhos),
    )
    sessao.add(conector)
    await sessao.flush()
    return conector


async def servidores_do_usuario(sessao: AsyncSession, usuario_id: UUID) -> list[ServidorMCP]:
    """Conectores ativos, com cabeçalhos decifrados (só dentro do worker)."""
    linhas = (
        await sessao.scalars(
            select(Conector).where(Conector.usuario_id == usuario_id, Conector.ativo.is_(True))
        )
    ).all()
    return [ServidorMCP(nome=c.nome, url=c.url, cabecalhos=decifrar_cabecalhos(c)) for c in linhas]


async def adicionar_servidor_mcp(args: AdicionarServidorMCP, contexto: ContextoFerramenta) -> str:
    if contexto.sem_supervisao:
        raise ErroFerramenta("Rotina sem supervisão não conecta servidores.")
    async with abrir_sessao() as sessao:
        conector = await criar_conector(
            sessao, contexto.usuario_id, args.nome, args.url, args.cabecalhos
        )
        return f"Servidor «{conector.nome}» conectado. As ferramentas aparecem na próxima mensagem."
