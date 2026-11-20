"""Rotas de APIs de modelos conectadas pelo usuário; especificação §§2 e 5."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, SecretStr
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import conexoes, reservas
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.llm.catalogo_chat import modelos_principais
from app.llm.provedores import PREFIXO_LITELLM, ConfigProvedor, listar_modelos
from app.llm.sonda import Sonda, sondar_capacidades
from app.modelos.esquemas import (
    ModeloSaida,
    ProvedorAtualizacao,
    ProvedorConexaoSaida,
    ProvedorCriacao,
    ProvedorSaida,
)
from app.modelos.tabelas import ChaveProvedor
from app.seletor.catalogo import obter_catalogo
from app.seletor.repositorio import config_do_provedor

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


def obter_sonda() -> Sonda:
    """Teste de capacidades dos modelos fora do catálogo; testes substituem para não usar a rede."""
    return sondar_capacidades


SondaDep = Annotated[Sonda, Depends(obter_sonda)]


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
    sonda: SondaDep,
) -> ProvedorConexaoSaida:
    """Testa, cifra e cadastra uma API de modelos."""
    provedor, modelos = await conexoes.conectar(sessao, redis, usuario_id, dados, listador, sonda)
    return ProvedorConexaoSaida(
        provedor=_saida(provedor),
        modelos=[
            ModeloSaida.de_linha(modelo).model_copy(
                update={
                    "principal": modelo.modelo in modelos_principais([m.modelo for m in modelos])
                }
            )
            for modelo in modelos
        ],
    )


class ModeloAdicao(BaseModel):
    id: str = Field(min_length=1, max_length=200)


@roteador.post("/{provedor_id}/modelos", status_code=status.HTTP_201_CREATED)
async def adicionar_modelo(
    provedor_id: UUID,
    dados: ModeloAdicao,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
    listador: ListadorDep,
) -> ModeloSaida:
    """Confere o catálogo remoto (sem geração paga), normaliza o ID e adiciona para o dono."""

    provedor = await conexoes._provedor_do_usuario(sessao, usuario_id, provedor_id)
    # Serializa adições para não disputar o limite e a restrição única.
    await sessao.refresh(provedor, with_for_update=True)
    prefixo = PREFIXO_LITELLM[provedor.tipo] + "/"
    nome = dados.id.strip()
    if not nome or any(c.isspace() for c in nome):
        raise conexoes.ErroDadosProvedor("Informe um ID de modelo válido, sem espaços.")
    if not nome.startswith(prefixo):
        nome = prefixo + nome
    existentes = await conexoes._modelos_do(sessao, provedor.id)
    linha = next((m for m in existentes if m.modelo == nome), None)
    if linha is None:
        if len(existentes) >= conexoes.MAX_MODELOS:
            raise conexoes.ErroDadosProvedor("Este provedor já tem o limite de 500 modelos.")
        config = await config_do_provedor(sessao, usuario_id, provedor.id)
        nomes = await conexoes._testar(redis, usuario_id, config, listador)
        if nome not in nomes:
            raise conexoes.ErroDadosProvedor("Esse modelo não está disponível neste provedor.")
        linha = conexoes._novo_modelo(provedor.id, obter_catalogo().classificar(nome))
        sessao.add(linha)
        await sessao.flush()
    principais = modelos_principais([m.modelo for m in existentes] + [nome])
    return ModeloSaida.de_linha(linha).model_copy(update={"principal": nome in principais})


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
    sonda: SondaDep,
) -> ProvedorSaida:
    """Troca chave ou teto mensal de um provedor."""
    provedor = await conexoes.atualizar(
        sessao, redis, usuario_id, provedor_id, dados, listador, sonda
    )
    return _saida(provedor)


@roteador.delete("/{provedor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_provedor(provedor_id: UUID, usuario_id: Usuario, sessao: Sessao) -> None:
    """Remove logicamente um provedor e sua chave cifrada."""
    await conexoes.apagar(sessao, usuario_id, provedor_id)


# ---------- chaves extras (migração 0019) ----------


class ChaveExtraEntrada(BaseModel):
    chave: SecretStr = Field(max_length=4_000)


class ChaveExtraSaida(BaseModel):
    id: UUID
    chave_final: str | None
    criado_em: datetime


def _saida_chave(linha: ChaveProvedor) -> ChaveExtraSaida:
    return ChaveExtraSaida(id=linha.id, chave_final=linha.chave_final, criado_em=linha.criado_em)


@roteador.get("/{provedor_id}/chaves")
async def listar_chaves_extras(
    provedor_id: UUID, usuario_id: Usuario, sessao: Sessao
) -> list[ChaveExtraSaida]:
    """Chaves extras da conexão (só o final de cada uma)."""
    return [_saida_chave(c) for c in await reservas.listar_chaves(sessao, usuario_id, provedor_id)]


@roteador.post("/{provedor_id}/chaves", status_code=status.HTTP_201_CREATED)
async def adicionar_chave_extra(
    provedor_id: UUID,
    dados: ChaveExtraEntrada,
    usuario_id: Usuario,
    sessao: Sessao,
    redis: RedisDep,
    listador: ListadorDep,
) -> ChaveExtraSaida:
    """Testa e guarda outra chave da mesma conexão; o mesmo modelo continua com ela no limite."""
    linha = await reservas.adicionar_chave(
        sessao, redis, usuario_id, provedor_id, dados.chave, listador
    )
    return _saida_chave(linha)


@roteador.delete("/{provedor_id}/chaves/{chave_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_chave_extra(
    provedor_id: UUID, chave_id: UUID, usuario_id: Usuario, sessao: Sessao
) -> None:
    await reservas.remover_chave(sessao, usuario_id, provedor_id, chave_id)
