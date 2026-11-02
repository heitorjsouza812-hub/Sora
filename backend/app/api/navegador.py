"""Perfis do navegador persistente para o app (Leme, etapa 4).

Nunca devolve cookies nem o estado cifrado: só o nome, o tipo e os domínios que o usuário
aprovou. Registrado antes de ``equipe`` para valer sobre as rotas de perfil de lá.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.modelos.tabelas import Agente, EstadoNavegador, PerfilNavegador
from app.navegador.perfis import (
    TipoPerfil,
    cifrar_estado,
    decifrar_estado,
    dominios_aprovados,
    ler_particao,
    sem_dominio_aprovado,
)

roteador = APIRouter(prefix="/navegador", tags=["navegador"])
Usuario = Annotated[UUID, Depends(usuario_atual)]
Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]


class PerfilNavegadorSaida(BaseModel):
    perfil_id: UUID
    nome: str
    tipo: Literal["compartilhado", "agente", "nomeado"]
    dominios_aprovados: list[str]
    criado_em: datetime
    atualizado_em: datetime


def id_da_particao(particao: str) -> UUID:
    """Identificador estável para perfis que não têm linha própria (compartilhado, por agente)."""
    return uuid5(NAMESPACE_URL, f"sora:perfil:{particao}")


async def _estados(sessao: AsyncSession, usuario_id: UUID) -> list[EstadoNavegador]:
    consulta = select(EstadoNavegador).where(EstadoNavegador.usuario_id == usuario_id)
    return list((await sessao.scalars(consulta)).all())


def _dominios(estado: EstadoNavegador) -> list[str]:
    try:
        dados = decifrar_estado(
            estado.estado_cifrado, usuario_id=estado.usuario_id, particao_=estado.particao
        )
    except Exception:
        return []
    return sorted(dominios_aprovados(dados))


@roteador.get("/perfis")
async def listar_perfis(usuario_id: Usuario, sessao: Sessao) -> list[PerfilNavegadorSaida]:
    estados = {e.particao: e for e in await _estados(sessao, usuario_id)}
    nomeados = list(
        (
            await sessao.scalars(
                select(PerfilNavegador)
                .where(PerfilNavegador.usuario_id == usuario_id)
                .order_by(PerfilNavegador.nome)
            )
        ).all()
    )
    agentes = {
        hashlib.sha256(str(a.id).encode()).hexdigest()[:32]: a
        for a in await sessao.scalars(
            select(Agente).where(Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None))
        )
    }
    saida: list[PerfilNavegadorSaida] = []
    nomeados_vistos: set[UUID] = set()
    for particao, estado in sorted(estados.items()):
        lida = ler_particao(particao)
        if lida is None or lida.usuario_id != usuario_id:
            continue
        if lida.tipo is TipoPerfil.NOMEADO:
            perfil = next((p for p in nomeados if p.id == lida.perfil_id), None)
            if perfil is None:
                continue
            nomeados_vistos.add(perfil.id)
            saida.append(
                PerfilNavegadorSaida(
                    perfil_id=perfil.id,
                    nome=perfil.nome,
                    tipo="nomeado",
                    dominios_aprovados=_dominios(estado),
                    criado_em=perfil.criado_em,
                    atualizado_em=estado.atualizado_em,
                )
            )
            continue
        if lida.tipo is TipoPerfil.AGENTE:
            agente = agentes.get(particao.rsplit("-", 1)[-1])
            if agente is None:
                continue
            nome, tipo = f"Agente {agente.nome}", "agente"
        else:
            nome, tipo = "Compartilhado", "compartilhado"
        saida.append(
            PerfilNavegadorSaida(
                perfil_id=id_da_particao(particao),
                nome=nome,
                tipo=tipo,  # type: ignore[arg-type]
                dominios_aprovados=_dominios(estado),
                criado_em=estado.atualizado_em,
                atualizado_em=estado.atualizado_em,
            )
        )
    for perfil in nomeados:  # perfil criado, ainda sem login salvo
        if perfil.id not in nomeados_vistos:
            saida.append(
                PerfilNavegadorSaida(
                    perfil_id=perfil.id,
                    nome=perfil.nome,
                    tipo="nomeado",
                    dominios_aprovados=[],
                    criado_em=perfil.criado_em,
                    atualizado_em=perfil.criado_em,
                )
            )
    return saida


async def _achar(
    sessao: AsyncSession, usuario_id: UUID, perfil_id: UUID
) -> tuple[str, PerfilNavegador | None]:
    """Partição e (se nomeado) a linha do perfil; 404 se não for deste usuário."""
    nomeado = await sessao.scalar(
        select(PerfilNavegador).where(
            PerfilNavegador.id == perfil_id, PerfilNavegador.usuario_id == usuario_id
        )
    )
    if nomeado is not None:
        return f"u{usuario_id.hex}-perfil-{nomeado.id.hex}", nomeado
    for estado in await _estados(sessao, usuario_id):
        if id_da_particao(estado.particao) == perfil_id:
            return estado.particao, None
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Perfil não encontrado.")


@roteador.delete("/perfis/{perfil_id}", status_code=204)
async def apagar_perfil(perfil_id: UUID, usuario_id: Usuario, sessao: Sessao) -> None:
    particao, nomeado = await _achar(sessao, usuario_id, perfil_id)
    await sessao.execute(
        delete(EstadoNavegador).where(
            EstadoNavegador.particao == particao, EstadoNavegador.usuario_id == usuario_id
        )
    )
    if nomeado is not None:
        await sessao.execute(
            update(Agente)
            .where(Agente.perfil_navegador_id == nomeado.id)
            .values(perfil_navegador="compartilhado", perfil_navegador_id=None)
        )
        await sessao.delete(nomeado)
    await sessao.commit()


@roteador.delete("/perfis/{perfil_id}/dominios/{dominio}", status_code=204)
async def revogar_dominio(
    perfil_id: UUID, dominio: str, usuario_id: Usuario, sessao: Sessao
) -> None:
    particao, _ = await _achar(sessao, usuario_id, perfil_id)
    estado = await sessao.get(EstadoNavegador, particao, with_for_update=True)
    dominio = dominio.strip().lower()
    if estado is None or dominio not in _dominios(estado):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Domínio não está aprovado neste perfil.")
    dados = decifrar_estado(estado.estado_cifrado, usuario_id=usuario_id, particao_=particao)
    estado.estado_cifrado = cifrar_estado(
        sem_dominio_aprovado(dados, dominio), usuario_id=usuario_id, particao_=particao
    )
    estado.atualizado_em = datetime.now(UTC)
    await sessao.commit()
