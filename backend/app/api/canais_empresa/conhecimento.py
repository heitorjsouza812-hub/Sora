"""Base de conhecimento da empresa (sem dado pessoal): listar, editar, aprovar."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.canais_empresa.comum import (
    RedisDep,
    Sessao,
    Usuario,
    roteador,
)
from app.api.canais_empresa.esquemas import (
    ConhecimentoEntrada,
    ConhecimentoSaida,
)
from app.canais_empresa import conhecimento as base
from app.canais_empresa.eventos import ConhecimentoAtualizado, publicar
from app.canais_empresa.extracao import CATEGORIAS
from app.canais_empresa.pii import anonimizar_para_conhecimento
from app.canais_empresa.tabelas import (
    ConhecimentoEmpresa,
)


def _saida_conhecimento(i: ConhecimentoEmpresa) -> ConhecimentoSaida:
    return ConhecimentoSaida(
        id=i.id,
        categoria=i.categoria,
        titulo=i.titulo,
        conteudo=i.conteudo,
        ocorrencias=i.ocorrencias,
        contraditorio=i.contraditorio,
        editado=i.travado,
        estado="aprovado" if i.estado == base.ESTADO_APROVADO else "pendente",
        aprovado_em=i.aprovado_em,
        no_prompt=base.entra_no_prompt(i),
        sem_resposta=not i.conteudo.strip(),
        em_disputa=i.em_disputa,
        anteriores=i.anteriores,
        origens=i.origens,
        primeira_em=i.primeira_em,
        ultima_em=i.ultima_em,
    )


@roteador.get("/conhecimento")
async def listar_conhecimento(
    usuario_id: Usuario,
    sessao: Sessao,
    busca: Annotated[str | None, Query(max_length=300)] = None,
    categoria: Annotated[str | None, Query()] = None,
    contraditorio: Annotated[bool | None, Query()] = None,
    estado: Annotated[Literal["pendente", "aprovado"] | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
) -> list[ConhecimentoSaida]:
    if categoria is not None and categoria not in CATEGORIAS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Categoria inválida.")
    if busca and busca.strip():
        itens = await base.buscar(
            sessao, usuario_id, busca, categoria=categoria, limite=limite + deslocamento
        )
        if contraditorio is not None:
            itens = [i for i in itens if i.contraditorio == contraditorio]
        if estado is not None:
            itens = [i for i in itens if i.estado == estado]
        return [_saida_conhecimento(i) for i in itens[deslocamento : deslocamento + limite]]
    consulta = select(ConhecimentoEmpresa).where(
        ConhecimentoEmpresa.usuario_id == usuario_id, ConhecimentoEmpresa.apagado_em.is_(None)
    )
    if categoria:
        consulta = consulta.where(ConhecimentoEmpresa.categoria == categoria)
    if contraditorio is not None:
        consulta = consulta.where(ConhecimentoEmpresa.contraditorio == contraditorio)
    if estado is not None:
        consulta = consulta.where(ConhecimentoEmpresa.estado == estado)
    itens = await sessao.scalars(
        consulta.order_by(
            ConhecimentoEmpresa.ocorrencias.desc(), ConhecimentoEmpresa.ultima_em.desc()
        )
        .limit(limite)
        .offset(deslocamento)
    )
    return [_saida_conhecimento(i) for i in itens.all()]


async def _item(sessao: AsyncSession, usuario_id: UUID, item_id: UUID) -> ConhecimentoEmpresa:
    i = await sessao.scalar(
        select(ConhecimentoEmpresa).where(
            ConhecimentoEmpresa.id == item_id,
            ConhecimentoEmpresa.usuario_id == usuario_id,
            ConhecimentoEmpresa.apagado_em.is_(None),
        )
    )
    if i is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item não encontrado.")
    return i


@roteador.patch("/conhecimento/{item_id}")
async def editar_conhecimento(
    item_id: UUID, dados: ConhecimentoEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> ConhecimentoSaida:
    """Editar o conteúdo ou a categoria trava o item (o aprendizado automático passa a só contar,
    sem sobrescrever), resolve a contradição e aprova o texto que o usuário escreveu. Só renomear
    o título não trava, não aprova e não apaga uma contradição aberta."""
    i = await _item(sessao, usuario_id, item_id)
    if dados.titulo is not None:
        i.titulo = anonimizar_para_conhecimento(" ".join(dados.titulo.split()))[:200]
    mudou_o_sentido = dados.conteudo is not None or dados.categoria is not None
    if dados.conteudo is not None:
        i.conteudo = anonimizar_para_conhecimento(" ".join(dados.conteudo.split()))[:800]
    if dados.categoria is not None:
        i.categoria = dados.categoria
    if mudou_o_sentido:
        i.chave = f"editado:{i.id}"
        i.travado = True
        i.contraditorio = False
        i.em_disputa = []
    i.atualizado_em = datetime.now(UTC)
    if mudou_o_sentido and i.conteudo.strip():
        base.aprovar(i)  # quem escreve o conteúdo está aprovando
    await sessao.commit()
    await publicar(redis, ConhecimentoAtualizado(motivo="edicao"), usuario_id)
    return _saida_conhecimento(i)


class AprovarEntrada(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=100)


class ResolverEntrada(BaseModel):
    versao: int | None = Field(default=None, ge=0)
    """``null`` mantém o conteúdo vigente; ``n`` adota ``em_disputa[n]``."""


@roteador.post("/conhecimento/aprovar")
async def aprovar_conhecimento_em_lote(
    dados: AprovarEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> list[ConhecimentoSaida]:
    """Aprova vários itens de uma vez (só valem para os bots depois disto). Item com
    contradição aberta ou sem resposta de funcionário responde 409 e nada é aprovado."""
    itens = [await _item(sessao, usuario_id, item_id) for item_id in dict.fromkeys(dados.ids)]
    try:
        for item in itens:
            base.aprovar(item)
    except base.ErroConhecimento as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from erro
    await sessao.commit()
    await publicar(redis, ConhecimentoAtualizado(motivo="aprovacao"), usuario_id)
    return [_saida_conhecimento(i) for i in itens]


@roteador.post("/conhecimento/{item_id}/aprovar")
async def aprovar_conhecimento(
    item_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> ConhecimentoSaida:
    i = await _item(sessao, usuario_id, item_id)
    try:
        base.aprovar(i)
    except base.ErroConhecimento as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from erro
    await sessao.commit()
    await publicar(redis, ConhecimentoAtualizado(motivo="aprovacao"), usuario_id)
    return _saida_conhecimento(i)


@roteador.post("/conhecimento/{item_id}/resolver")
async def resolver_conhecimento(
    item_id: UUID, dados: ResolverEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> ConhecimentoSaida:
    """Fecha a contradição: o usuário escolhe qual versão vale (e o item fica aprovado)."""
    i = await _item(sessao, usuario_id, item_id)
    try:
        base.resolver_contradicao(i, dados.versao)
    except base.ErroConhecimento as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from erro
    await sessao.commit()
    await publicar(redis, ConhecimentoAtualizado(motivo="aprovacao"), usuario_id)
    return _saida_conhecimento(i)


@roteador.delete("/conhecimento/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_conhecimento(
    item_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> None:
    """Esconde o item e impede que o aprendizado automático o traga de volta."""
    i = await _item(sessao, usuario_id, item_id)
    i.apagado_em = datetime.now(UTC)
    await sessao.commit()
    await publicar(redis, ConhecimentoAtualizado(motivo="remocao"), usuario_id)
