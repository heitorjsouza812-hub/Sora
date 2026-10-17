"""Rotas de APIs de modelos conectadas pelo usuário; especificação §§2 e 5."""

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import conexoes
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.llm.provedores import ConfigProvedor, listar_modelos
from app.modelos.esquemas import (
    ModeloSaida,
    ProvedorAtualizacao,
    ProvedorConexaoSaida,
    ProvedorCriacao,
    ProvedorSaida,
)

roteador = APIRouter(
    prefix="/provedores", tags=["provedores"], dependencies=[Depends(usuario_atual)]
)

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]
Usuario = Annotated[UUID, Depends(usuario_atual)]
Listador = Callable[[ConfigProvedor], Awaitable[list[str]]]


def obter_listador() -> Listador:
    """Devolve o listador real; testes substituem esta dependência para não usar a rede."""
    return listar_modelos


ListadorDep = Annotated[Listador, Depends(obter_listador)]


def _saida(provedor: object, gasto_mes_usd: Decimal = Decimal("0")) -> ProvedorSaida:
    return ProvedorSaida.model_validate(provedor).model_copy(
        update={"gasto_mes_usd": gasto_mes_usd}
    )


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def conectar_provedor(
    dados: ProvedorCriacao,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
    listador: ListadorDep,
) -> ProvedorConexaoSaida:
    """Testa, cifra e cadastra uma API de modelos."""
    provedor, modelos = await conexoes.conectar(sessao, redis, usuario_id, dados, listador)
    return ProvedorConexaoSaida(
        provedor=_saida(provedor),
        modelos=[ModeloSaida.model_validate(modelo) for modelo in modelos],
    )


@roteador.get("")
async def listar_provedores(usuario_id: Usuario, sessao: Sessao) -> list[ProvedorSaida]:
    """Lista provedores sem expor suas chaves."""
    itens = await conexoes.listar(sessao, usuario_id)
    return [_saida(provedor, gasto) for provedor, gasto in itens]


@roteador.patch("/{provedor_id}")
async def atualizar_provedor(
    provedor_id: UUID,
    dados: ProvedorAtualizacao,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
    listador: ListadorDep,
) -> ProvedorSaida:
    """Troca chave ou teto mensal de um provedor."""
    provedor = await conexoes.atualizar(sessao, redis, usuario_id, provedor_id, dados, listador)
    return _saida(provedor)


@roteador.delete("/{provedor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_provedor(provedor_id: UUID, usuario_id: Usuario, sessao: Sessao) -> None:
    """Remove logicamente um provedor e sua chave cifrada."""
    await conexoes.apagar(sessao, usuario_id, provedor_id)
