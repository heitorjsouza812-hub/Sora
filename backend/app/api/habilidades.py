"""Rotas das habilidades (receitas SKILL.md do usuário) para a tela de Configurações.

O corpo é o passo a passo em Markdown; o servidor monta e valida o SKILL.md. Contrato em
``.maestri/contrato-etapa4.md``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.ferramentas.base import ErroFerramenta
from app.habilidades import (
    MAX_CONTEUDO,
    MAX_DESCRICAO,
    MAX_NOME,
    ler_skill_md,
    montar_skill_md,
)
from app.modelos.tabelas import Habilidade

roteador = APIRouter(prefix="/habilidades", tags=["habilidades"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]
MAX_HABILIDADES = 100


class HabilidadeCriacao(BaseModel):
    nome: str = Field(min_length=1, max_length=MAX_NOME)
    descricao: str = Field(min_length=1, max_length=MAX_DESCRICAO)
    corpo: str = Field(min_length=1, max_length=MAX_CONTEUDO)


class HabilidadeAtualizacao(BaseModel):
    descricao: str | None = Field(default=None, min_length=1, max_length=MAX_DESCRICAO)
    corpo: str | None = Field(default=None, min_length=1, max_length=MAX_CONTEUDO)


class HabilidadeSaida(BaseModel):
    id: UUID
    nome: str
    descricao: str
    corpo: str
    origem: str
    criada_em: datetime
    atualizada_em: datetime


def _saida(h: Habilidade) -> HabilidadeSaida:
    try:
        corpo = ler_skill_md(h.conteudo).corpo
    except ErroFerramenta:
        corpo = h.conteudo
    return HabilidadeSaida(
        id=h.id,
        nome=h.nome,
        descricao=h.descricao,
        corpo=corpo,
        origem=h.origem,
        criada_em=h.criada_em,
        atualizada_em=h.atualizada_em,
    )


async def _obter(sessao: AsyncSession, usuario_id: UUID, habilidade_id: UUID) -> Habilidade:
    habilidade = await sessao.scalar(
        select(Habilidade).where(
            Habilidade.id == habilidade_id, Habilidade.usuario_id == usuario_id
        )
    )
    if habilidade is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Habilidade não encontrada.")
    return habilidade


@roteador.get("")
async def listar_habilidades(usuario_id: UsuarioId, sessao: Sessao) -> list[HabilidadeSaida]:
    linhas = (
        await sessao.scalars(
            select(Habilidade).where(Habilidade.usuario_id == usuario_id).order_by(Habilidade.nome)
        )
    ).all()
    return [_saida(h) for h in linhas]


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def criar_habilidade(
    dados: HabilidadeCriacao, usuario_id: UsuarioId, sessao: Sessao
) -> HabilidadeSaida:
    total = await sessao.scalar(
        select(func.count()).select_from(Habilidade).where(Habilidade.usuario_id == usuario_id)
    )
    if (total or 0) >= MAX_HABILIDADES:
        raise HTTPException(422, f"No máximo {MAX_HABILIDADES} habilidades.")
    try:
        conteudo = montar_skill_md(dados.nome, dados.descricao, dados.corpo)
    except ErroFerramenta as erro:
        raise HTTPException(422, str(erro)) from erro
    habilidade = Habilidade(
        usuario_id=usuario_id,
        nome=dados.nome.strip(),
        descricao=dados.descricao.strip(),
        conteudo=conteudo,
    )
    sessao.add(habilidade)
    try:
        await sessao.flush()
    except IntegrityError as erro:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Já existe uma habilidade com esse nome."
        ) from erro
    return _saida(habilidade)


@roteador.patch("/{habilidade_id}")
async def atualizar_habilidade(
    habilidade_id: UUID, dados: HabilidadeAtualizacao, usuario_id: UsuarioId, sessao: Sessao
) -> HabilidadeSaida:
    habilidade = await _obter(sessao, usuario_id, habilidade_id)
    atual = ler_skill_md(habilidade.conteudo)
    descricao = (dados.descricao or habilidade.descricao).strip()
    corpo = dados.corpo if dados.corpo is not None else atual.corpo
    try:
        habilidade.conteudo = montar_skill_md(habilidade.nome, descricao, corpo, atual.frontmatter)
    except ErroFerramenta as erro:
        raise HTTPException(422, str(erro)) from erro
    habilidade.descricao = descricao
    habilidade.atualizada_em = func.now()
    await sessao.flush()
    await sessao.refresh(habilidade)
    return _saida(habilidade)


@roteador.delete("/{habilidade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_habilidade(habilidade_id: UUID, usuario_id: UsuarioId, sessao: Sessao) -> None:
    await sessao.delete(await _obter(sessao, usuario_id, habilidade_id))
