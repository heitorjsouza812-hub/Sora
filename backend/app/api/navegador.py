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
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.eventos.equipe import AbaNavegadorEvento
from app.ferramentas.base import ErroFerramenta
from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import Agente, EstadoNavegador, PerfilNavegador
from app.navegador.perfis import (
    PerfilNomeado,
    TipoPerfil,
    cifrar_estado,
    decifrar_estado,
    dominios_aprovados,
    ler_particao,
    novo_perfil,
    sem_dominio_aprovado,
)
from workers.fila import obter_fila

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


# ---------- criar perfil e abrir aba para o usuário logar ----------


class PerfilEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=60)


class AbaDoPerfilEntrada(BaseModel):
    url: str = Field(min_length=8, max_length=2_000, pattern=r"^https?://")
    agente_id: UUID | None = Field(
        default=None, description="Dono da aba; sem ele vale a Sora da conta."
    )


@roteador.post("/perfis", status_code=201)
async def criar_perfil(
    dados: PerfilEntrada, usuario_id: Usuario, sessao: Sessao
) -> PerfilNavegadorSaida:
    existentes = [
        PerfilNomeado(id=p.id, usuario_id=p.usuario_id, nome=p.nome, cor=p.cor)
        for p in await sessao.scalars(
            select(PerfilNavegador).where(PerfilNavegador.usuario_id == usuario_id)
        )
    ]
    try:
        novo = novo_perfil(usuario_id, dados.nome, existentes)
    except ErroFerramenta as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from erro
    linha = PerfilNavegador(id=novo.id, usuario_id=usuario_id, nome=novo.nome, cor=novo.cor)
    sessao.add(linha)
    await sessao.commit()
    await sessao.refresh(linha)
    return PerfilNavegadorSaida(
        perfil_id=linha.id,
        nome=linha.nome,
        tipo="nomeado",
        dominios_aprovados=[],
        criado_em=linha.criado_em,
        atualizado_em=linha.criado_em,
    )


@roteador.post("/perfis/{perfil_id}/abrir", status_code=202)
async def abrir_aba_no_perfil(
    perfil_id: UUID, dados: AbaDoPerfilEntrada, usuario_id: Usuario, sessao: Sessao
) -> AbaNavegadorEvento:
    """Abre (no worker) uma aba do perfil, já assumida pelo usuário, para ele fazer o login."""
    perfil = await sessao.scalar(
        select(PerfilNavegador).where(
            PerfilNavegador.id == perfil_id, PerfilNavegador.usuario_id == usuario_id
        )
    )
    if perfil is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Perfil não encontrado.")
    consulta = select(Agente.id).where(Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None))
    consulta = (
        consulta.where(Agente.id == dados.agente_id)
        if dados.agente_id
        else consulta.where(Agente.tipo == TipoAgente.SORA)
    )
    agente_id = await sessao.scalar(consulta.limit(1))
    if agente_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente não encontrado.")
    fila = await obter_fila()
    job = await fila.enqueue_job(
        "abrir_aba_de_perfil", str(usuario_id), str(agente_id), str(perfil.id), dados.url
    )
    if job is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um pedido igual em andamento.")
    try:
        estado = await job.result(timeout=60)
    except TimeoutError as erro:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "O navegador não respondeu a tempo."
        ) from erro
    except Exception as erro:
        raise HTTPException(
            status.HTTP_409_CONFLICT, str(erro) or "Não consegui abrir a aba."
        ) from erro
    return AbaNavegadorEvento(**estado)


# ---------- qual perfil cada agente usa ----------

roteador_agente = APIRouter(tags=["navegador"])


class EscolhaPerfilEntrada(BaseModel):
    tipo: Literal["efemero", "compartilhado", "perfil"]
    perfil_id: UUID | None = None


class EscolhaPerfilSaida(BaseModel):
    agente_id: UUID
    tipo: Literal["efemero", "compartilhado", "agente", "perfil"]
    perfil_id: UUID | None = None
    perfil_nome: str | None = None


_TIPO_NO_BANCO = {"efemero": "efemero", "compartilhado": "compartilhado", "perfil": "nomeado"}


async def _agente_da_conta(sessao: AsyncSession, usuario_id: UUID, agente_id: UUID) -> Agente:
    agente = await sessao.scalar(
        select(Agente).where(
            Agente.id == agente_id, Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None)
        )
    )
    if agente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agente não encontrado.")
    return agente


async def _escolha(sessao: AsyncSession, agente: Agente) -> EscolhaPerfilSaida:
    nome = None
    if agente.perfil_navegador_id is not None:
        nome = await sessao.scalar(
            select(PerfilNavegador.nome).where(PerfilNavegador.id == agente.perfil_navegador_id)
        )
    tipo = "perfil" if agente.perfil_navegador == "nomeado" else agente.perfil_navegador
    return EscolhaPerfilSaida(
        agente_id=agente.id,
        tipo=tipo,  # type: ignore[arg-type]
        perfil_id=agente.perfil_navegador_id,
        perfil_nome=nome,
    )


@roteador_agente.get("/agentes/{agente_id}/navegador")
async def perfil_do_agente(
    agente_id: UUID, usuario_id: Usuario, sessao: Sessao
) -> EscolhaPerfilSaida:
    return await _escolha(sessao, await _agente_da_conta(sessao, usuario_id, agente_id))


@roteador_agente.put("/agentes/{agente_id}/navegador")
async def escolher_perfil_do_agente(
    agente_id: UUID, dados: EscolhaPerfilEntrada, usuario_id: Usuario, sessao: Sessao
) -> EscolhaPerfilSaida:
    agente = await _agente_da_conta(sessao, usuario_id, agente_id)
    if dados.tipo == "perfil":
        if dados.perfil_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Informe o perfil_id.")
        existe = await sessao.scalar(
            select(PerfilNavegador.id).where(
                PerfilNavegador.id == dados.perfil_id, PerfilNavegador.usuario_id == usuario_id
            )
        )
        if existe is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Perfil não encontrado.")
        agente.perfil_navegador_id = dados.perfil_id
    else:
        agente.perfil_navegador_id = None
    agente.perfil_navegador = _TIPO_NO_BANCO[dados.tipo]
    await sessao.commit()
    return await _escolha(sessao, agente)
