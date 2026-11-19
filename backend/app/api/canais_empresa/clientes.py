"""Clientes e fichas (fatos por cliente), com "apagar tudo deste cliente" (LGPD)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.canais_empresa.comum import (
    RedisDep,
    Sessao,
    Usuario,
    roteador,
)
from app.api.canais_empresa.esquemas import (
    ClienteEntrada,
    ClienteResumo,
    FatoEntrada,
    FatoSaida,
    FichaSaida,
)
from app.canais_empresa import lgpd
from app.canais_empresa.eventos import ClienteAtualizado, ConhecimentoAtualizado, publicar
from app.canais_empresa.pii import mascarar_pii
from app.canais_empresa.tabelas import (
    ContatoEmpresa,
    FatoCliente,
)


def _fato_saida(f: FatoCliente) -> FatoSaida:
    return FatoSaida(
        id=f.id,
        tipo=f.tipo,
        texto=f.texto,
        data_referencia=f.data_referencia,
        origem_canal=f.origem_canal,
        origem_link=f.origem_link,
        origem_externo_id=f.origem_externo_id,
        editado=f.editado,
        criado_em=f.criado_em,
    )


@roteador.get("/clientes")
async def listar_clientes(
    usuario_id: Usuario,
    sessao: Sessao,
    busca: Annotated[str | None, Query(max_length=120)] = None,
    canal: Annotated[Literal["slack", "whatsapp"] | None, Query()] = None,
    papel: Annotated[Literal["cliente", "funcionario"], Query()] = "cliente",
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
) -> list[ClienteResumo]:
    total = (
        select(FatoCliente.contato_id, func.count().label("n"))
        .where(FatoCliente.usuario_id == usuario_id)
        .group_by(FatoCliente.contato_id)
        .subquery()
    )
    consulta = (
        select(ContatoEmpresa, func.coalesce(total.c.n, 0))
        .outerjoin(total, total.c.contato_id == ContatoEmpresa.id)
        .where(ContatoEmpresa.usuario_id == usuario_id, ContatoEmpresa.papel == papel)
    )
    if canal:
        consulta = consulta.where(ContatoEmpresa.canal == canal)
    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        consulta = consulta.where(
            ContatoEmpresa.nome.ilike(termo) | ContatoEmpresa.id_externo.ilike(termo)
        )
    linhas = await sessao.execute(
        consulta.order_by(ContatoEmpresa.ultima_mensagem_em.desc().nulls_last(), ContatoEmpresa.id)
        .limit(limite)
        .offset(deslocamento)
    )
    return [
        ClienteResumo(
            id=c.id,
            canal=c.canal,
            nome=c.nome,
            id_externo=c.id_externo,
            papel=c.papel,
            ultima_mensagem_em=c.ultima_mensagem_em,
            total_fatos=n,
        )
        for c, n in linhas.all()
    ]


async def _contato(sessao: AsyncSession, usuario_id: UUID, contato_id: UUID) -> ContatoEmpresa:
    c = await sessao.scalar(
        select(ContatoEmpresa).where(
            ContatoEmpresa.id == contato_id, ContatoEmpresa.usuario_id == usuario_id
        )
    )
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    return c


async def _ficha(sessao: AsyncSession, c: ContatoEmpresa) -> FichaSaida:
    fatos = (
        await sessao.scalars(
            select(FatoCliente)
            .where(FatoCliente.contato_id == c.id, FatoCliente.usuario_id == c.usuario_id)
            .order_by(FatoCliente.tipo, FatoCliente.criado_em)
        )
    ).all()
    return FichaSaida(
        id=c.id,
        canal=c.canal,
        nome=c.nome,
        id_externo=c.id_externo,
        papel=c.papel,
        ultima_mensagem_em=c.ultima_mensagem_em,
        total_fatos=len(fatos),
        fatos=[_fato_saida(f) for f in fatos],
    )


@roteador.get("/clientes/{contato_id}")
async def ver_cliente(contato_id: UUID, usuario_id: Usuario, sessao: Sessao) -> FichaSaida:
    return await _ficha(sessao, await _contato(sessao, usuario_id, contato_id))


@roteador.patch("/clientes/{contato_id}")
async def editar_cliente(
    contato_id: UUID, dados: ClienteEntrada, usuario_id: Usuario, sessao: Sessao
) -> FichaSaida:
    c = await _contato(sessao, usuario_id, contato_id)
    if dados.nome is not None:
        c.nome = mascarar_pii(dados.nome.strip())
    if dados.papel is not None:
        c.papel = dados.papel
    await sessao.flush()
    return await _ficha(sessao, c)


@roteador.delete("/clientes/{contato_id}")
async def apagar_cliente(
    contato_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> dict[str, int]:
    """LGPD: apaga a ficha, as mensagens e o que a Sora aprendeu a partir deste cliente."""
    contato = await _contato(sessao, usuario_id, contato_id)
    canal = contato.canal
    contagem = await lgpd.apagar_cliente(sessao, usuario_id, contato_id)
    if contagem is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado.")
    await sessao.commit()
    await publicar(
        redis,
        ClienteAtualizado(contato_id=contato_id, canal=canal, motivo="apagado"),
        usuario_id,
    )
    if contagem["conhecimento_limpo"] or contagem["conhecimento_removido"]:
        await publicar(redis, ConhecimentoAtualizado(motivo="remocao"), usuario_id)
    return contagem


async def _fato(sessao: AsyncSession, usuario_id: UUID, fato_id: UUID) -> FatoCliente:
    f = await sessao.scalar(
        select(FatoCliente).where(FatoCliente.id == fato_id, FatoCliente.usuario_id == usuario_id)
    )
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fato não encontrado.")
    return f


async def _total_fatos(sessao: AsyncSession, contato_id: UUID) -> int:
    return (
        await sessao.scalar(
            select(func.count())
            .select_from(FatoCliente)
            .where(FatoCliente.contato_id == contato_id)
        )
        or 0
    )


@roteador.patch("/fatos/{fato_id}")
async def editar_fato(
    fato_id: UUID, dados: FatoEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> FatoSaida:
    f = await _fato(sessao, usuario_id, fato_id)
    if dados.texto is not None:
        f.texto = mascarar_pii(" ".join(dados.texto.split()))[:300]
    if dados.tipo is not None:
        f.tipo = dados.tipo
    if dados.limpar_data:
        f.data_referencia = None
    elif dados.data_referencia is not None:
        f.data_referencia = dados.data_referencia
    f.editado = True
    f.atualizado_em = datetime.now(UTC)
    await sessao.commit()
    contato = await sessao.get(ContatoEmpresa, f.contato_id)
    await publicar(
        redis,
        ClienteAtualizado(
            contato_id=f.contato_id,
            canal=contato.canal if contato else "",
            total_fatos=await _total_fatos(sessao, f.contato_id),
            motivo="edicao",
        ),
        usuario_id,
    )
    return _fato_saida(f)


@roteador.delete("/fatos/{fato_id}", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_fato(fato_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep) -> None:
    f = await _fato(sessao, usuario_id, fato_id)
    contato_id = f.contato_id
    contato = await sessao.get(ContatoEmpresa, contato_id)
    await sessao.delete(f)
    await sessao.commit()
    await publicar(
        redis,
        ClienteAtualizado(
            contato_id=contato_id,
            canal=contato.canal if contato else "",
            total_fatos=await _total_fatos(sessao, contato_id),
            motivo="remocao",
        ),
        usuario_id,
    )
