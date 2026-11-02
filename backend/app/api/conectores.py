"""Rotas dos conectores MCP (Relógio, etapa 4): listar, adicionar, ativar/desativar, remover e
testar. Cabeçalhos (tokens) entram cifrados e nunca voltam. Contrato em
``.maestri/contrato-etapa4.md``."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conectores.ferramenta import ambiente_local, criar_conector, decifrar_cabecalhos
from app.conectores.servidores import AdicionarServidorMCP, ServidorMCP, carregar_ferramentas
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.core.redacao import sanitizar_erro
from app.ferramentas.base import ErroFerramenta
from app.modelos.tabelas import Conector

roteador = APIRouter(prefix="/conectores", tags=["conectores"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]
RedisDep = Annotated[Redis, Depends(obter_redis)]

PRAZO_TESTE_S = 20
VALIDADE_ESTADO_S = 30 * 24 * 3600


class ConectorCriacao(BaseModel):
    nome: str = Field(min_length=1, max_length=40)
    url: str = Field(min_length=8, max_length=2_000)
    cabecalhos: dict[str, str] = Field(default_factory=dict)


class ConectorAtualizacao(BaseModel):
    ativo: bool


class ConectorSaida(BaseModel):
    id: UUID
    nome: str
    url: str
    ativo: bool
    tem_cabecalhos: bool
    estado: Literal["desconhecido", "ok", "erro"]
    n_ferramentas: int
    ultimo_erro: str | None
    criado_em: datetime


class ResultadoTeste(BaseModel):
    ok: bool
    ferramentas: list[str]
    erro: str | None


def _chave_estado(conector_id: UUID) -> str:
    return f"conector:estado:{conector_id}"


async def _estado(redis: Redis, conector_id: UUID) -> dict:
    bruto = await redis.get(_chave_estado(conector_id))
    if not bruto:
        return {}
    try:
        return json.loads(bruto)
    except ValueError:
        return {}


async def _saida(redis: Redis, conector: Conector) -> ConectorSaida:
    estado = await _estado(redis, conector.id)
    return ConectorSaida(
        id=conector.id,
        nome=conector.nome,
        url=conector.url,
        ativo=conector.ativo,
        tem_cabecalhos=bool(conector.cabecalhos_cifrados),
        estado=estado.get("estado", "desconhecido"),
        n_ferramentas=int(estado.get("n_ferramentas", 0)),
        ultimo_erro=estado.get("erro"),
        criado_em=conector.criado_em,
    )


async def _obter(sessao: AsyncSession, usuario_id: UUID, conector_id: UUID) -> Conector:
    conector = await sessao.scalar(
        select(Conector).where(Conector.id == conector_id, Conector.usuario_id == usuario_id)
    )
    if conector is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conector não encontrado.")
    return conector


@roteador.get("")
async def listar_conectores(
    usuario_id: UsuarioId, sessao: Sessao, redis: RedisDep
) -> list[ConectorSaida]:
    linhas = (
        await sessao.scalars(
            select(Conector).where(Conector.usuario_id == usuario_id).order_by(Conector.criado_em)
        )
    ).all()
    return [await _saida(redis, c) for c in linhas]


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def adicionar_conector(
    dados: ConectorCriacao, usuario_id: UsuarioId, sessao: Sessao, redis: RedisDep
) -> ConectorSaida:
    try:
        valido = AdicionarServidorMCP(nome=dados.nome, url=dados.url, cabecalhos=dados.cabecalhos)
        conector = await criar_conector(
            sessao, usuario_id, valido.nome, valido.url, valido.cabecalhos
        )
    except ValidationError as erro:
        raise HTTPException(422, erro.errors()[0]["msg"]) from erro
    except ErroFerramenta as erro:
        raise HTTPException(422, str(erro)) from erro
    return await _saida(redis, conector)


@roteador.patch("/{conector_id}")
async def atualizar_conector(
    conector_id: UUID,
    dados: ConectorAtualizacao,
    usuario_id: UsuarioId,
    sessao: Sessao,
    redis: RedisDep,
) -> ConectorSaida:
    conector = await _obter(sessao, usuario_id, conector_id)
    conector.ativo = dados.ativo
    await sessao.flush()
    return await _saida(redis, conector)


@roteador.delete("/{conector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_conector(
    conector_id: UUID, usuario_id: UsuarioId, sessao: Sessao, redis: RedisDep
) -> None:
    conector = await _obter(sessao, usuario_id, conector_id)
    await sessao.delete(conector)
    await redis.delete(_chave_estado(conector_id))


@roteador.post("/{conector_id}/testar")
async def testar_conector(
    conector_id: UUID, usuario_id: UsuarioId, sessao: Sessao, redis: RedisDep
) -> ResultadoTeste:
    conector = await _obter(sessao, usuario_id, conector_id)
    cabecalhos = decifrar_cabecalhos(conector)
    servidor = ServidorMCP(nome=conector.nome, url=conector.url, cabecalhos=cabecalhos)
    nomes: list[str] = []
    erro: str | None = None
    try:
        ferramentas = await asyncio.wait_for(
            carregar_ferramentas([servidor], ambiente_local=ambiente_local()), PRAZO_TESTE_S
        )
        nomes = [f.name for f in ferramentas]
        if not nomes:
            erro = "O servidor respondeu, mas não oferece ferramentas (ou recusou a conexão)."
    except Exception as falha:
        erro = sanitizar_erro(falha, list(cabecalhos.values()))[:300]
    ok = erro is None
    await redis.set(
        _chave_estado(conector.id),
        json.dumps({"estado": "ok" if ok else "erro", "n_ferramentas": len(nomes), "erro": erro}),
        ex=VALIDADE_ESTADO_S,
    )
    return ResultadoTeste(ok=ok, ferramentas=nomes, erro=erro)
