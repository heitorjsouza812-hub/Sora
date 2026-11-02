"""Rotas de consulta e cancelamento de cadeias; especificação §§2 e 6."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.eventos.streams import publicar_evento
from app.eventos.tipos import CadeiaAtualizada
from app.modelos.esquemas import CadeiaSaida
from app.orquestrador.cadeia import chave_de_cancelamento
from app.repositorios import cadeias as repositorio

roteador = APIRouter(prefix="/cadeias", tags=["cadeias"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]
Usuario = Annotated[UUID, Depends(usuario_atual)]


def _valor(valor: Any) -> Any:
    if hasattr(valor, "value"):
        return valor.value
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    if isinstance(valor, UUID):
        return str(valor)
    return float(valor) if valor.__class__.__name__ == "Decimal" else valor


def _linha(objeto: Any, campos: tuple[str, ...]) -> dict[str, Any]:
    return {campo: _valor(getattr(objeto, campo)) for campo in campos}


@roteador.get("/{cadeia_id}")
async def obter_cadeia(cadeia_id: UUID, usuario_id: Usuario, sessao: Sessao) -> CadeiaSaida:
    detalhe = await repositorio.detalhar(sessao, usuario_id, cadeia_id)
    if detalhe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cadeia não encontrada.")
    cadeia, etapas, passos = detalhe
    campos_etapa = (
        "id",
        "ordem",
        "depende_de",
        "especialista",
        "agente_id",
        "titulo",
        "nivel",
        "modelo",
        "tarefa",
        "saida",
        "status",
        "tentativa",
        "tokens",
        "custo_usd",
        "erro",
        "iniciada_em",
        "concluida_em",
    )
    campos_passo = (
        "id",
        "etapa_id",
        "agente_id",
        "tipo",
        "texto",
        "ferramenta",
        "acao",
        "parametros",
        "resultado",
        "para_agente_id",
        "status",
        "iniciado_em",
        "concluido_em",
    )
    return CadeiaSaida(
        id=cadeia.id,
        status=cadeia.status,
        plano=cadeia.plano,
        etapas=[_linha(etapa, campos_etapa) for etapa in etapas],
        passos=[_linha(passo, campos_passo) for passo in passos],
        modelos=list(dict.fromkeys(e.modelo for e in etapas if e.modelo)),
        tokens_usados=cadeia.tokens_usados,
        custo_usd=float(cadeia.custo_usd),
    )


@roteador.post("/{cadeia_id}/cancelar", status_code=status.HTTP_202_ACCEPTED)
async def cancelar_cadeia(
    cadeia_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> None:
    cadeia = await repositorio.cancelar(sessao, usuario_id, cadeia_id)
    if cadeia is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cadeia não encontrada.")
    await sessao.commit()
    await redis.set(chave_de_cancelamento(cadeia_id), "1", ex=24 * 60 * 60)
    await publicar_evento(
        redis,
        CadeiaAtualizada(
            cadeia_id=cadeia.id,
            status=cadeia.status,
            tokens_usados=cadeia.tokens_usados,
            custo_usd=float(cadeia.custo_usd),
        ),
        cadeia.conversa_id,
        usuario_id,
    )
