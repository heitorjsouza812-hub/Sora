"""Resumo no worker: mensagens lidas, agrupadas por conversa, viram ficha do cliente e
conhecimento da empresa.

``processar_pendentes`` não depende do ARQ: recebe a fábrica de sessões, o Redis dos eventos e o
extrator, então os testes rodam com um modelo falso. As mensagens só ficam como processadas
depois que a extração deu certo (se o modelo cair, a próxima passada tenta de novo).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update

from app.canais_empresa import conhecimento as base
from app.canais_empresa.eventos import ClienteAtualizado, ConhecimentoAtualizado, publicar
from app.canais_empresa.extracao import (
    Extracao,
    MensagemParaExtrair,
    extrair_com_modelo,
    extrair_heuristico,
    sanear,
)
from app.canais_empresa.tabelas import ContatoEmpresa, FatoCliente, MensagemEmpresa

registro = logging.getLogger(__name__)

MENSAGENS_POR_CHAMADA = 40
CONTEXTO_ANTERIOR = 6
LIMITE_POR_PASSADA = 400

Extrator = Callable[[list[MensagemParaExtrair]], Awaitable[Extracao]]


@dataclass(slots=True)
class ResultadoDaPassada:
    mensagens: int = 0
    fatos_novos: int = 0
    conhecimento_novo: int = 0
    conhecimento_atualizado: int = 0
    falhas: int = 0


async def extrator_do_usuario(sessao: Any, usuario_id: UUID) -> Extrator:
    """Extrator real: modelo do usuário (papel ``sora``, dificuldade 1, sem ferramentas). Com o
    modelo falso de desenvolvimento, as regras simples de ``extrair_heuristico``."""
    from app.llm.falso import modelo_falso_ativo

    if modelo_falso_ativo():

        async def heuristico(mensagens: list[MensagemParaExtrair]) -> Extracao:
            return extrair_heuristico(mensagens)

        return heuristico

    from app.orquestrador.modelos import modelos_do_papel

    modelos = await modelos_do_papel(sessao, usuario_id, "sora", dificuldade=1, precisa=())

    async def com_modelo(mensagens: list[MensagemParaExtrair]) -> Extracao:
        return await extrair_com_modelo(modelos, mensagens)

    return com_modelo


def _fatia(lista: list[Any], tamanho: int) -> list[list[Any]]:
    return [lista[i : i + tamanho] for i in range(0, len(lista), tamanho)]


async def processar_usuario(
    fabrica: Any,
    redis: Any,
    usuario_id: UUID,
    *,
    extrator: Extrator | None = None,
    contato_id: UUID | None = None,
) -> ResultadoDaPassada:
    """Processa as mensagens pendentes de um usuário (ou só de um contato)."""
    resultado = ResultadoDaPassada()
    async with fabrica() as sessao:
        filtro = [
            MensagemEmpresa.usuario_id == usuario_id,
            MensagemEmpresa.processada_em.is_(None),
            MensagemEmpresa.texto.is_not(None),
        ]
        if contato_id is not None:
            filtro.append(MensagemEmpresa.contato_id == contato_id)
        pendentes = list(
            (
                await sessao.scalars(
                    select(MensagemEmpresa)
                    .where(*filtro)
                    .order_by(MensagemEmpresa.enviada_em)
                    .limit(LIMITE_POR_PASSADA)
                )
            ).all()
        )
        if not pendentes:
            return resultado
        if extrator is None:
            extrator = await extrator_do_usuario(sessao, usuario_id)
        por_fio: dict[str, list[MensagemEmpresa]] = defaultdict(list)
        for m in pendentes:
            por_fio[m.fio].append(m)
        contatos = {
            c.id: c
            for c in (
                await sessao.scalars(
                    select(ContatoEmpresa).where(
                        ContatoEmpresa.id.in_({m.contato_id for m in pendentes}),
                        ContatoEmpresa.usuario_id == usuario_id,
                    )
                )
            ).all()
        }
        fatos_por_contato: dict[UUID, int] = defaultdict(int)
        for fio, mensagens in por_fio.items():
            anteriores = list(
                reversed(
                    (
                        await sessao.scalars(
                            select(MensagemEmpresa)
                            .where(
                                MensagemEmpresa.usuario_id == usuario_id,
                                MensagemEmpresa.fio == fio,
                                MensagemEmpresa.processada_em.is_not(None),
                                MensagemEmpresa.texto.is_not(None),
                                MensagemEmpresa.enviada_em < mensagens[0].enviada_em,
                            )
                            .order_by(MensagemEmpresa.enviada_em.desc())
                            .limit(CONTEXTO_ANTERIOR)
                        )
                    ).all()
                )
            )
            for pedaco in _fatia(mensagens, MENSAGENS_POR_CHAMADA):
                try:
                    await _processar_pedaco(
                        sessao, usuario_id, extrator, anteriores + pedaco, pedaco, contatos,
                        resultado, fatos_por_contato,
                    )  # fmt: skip
                except Exception:
                    registro.exception("falha ao resumir a conversa %s", fio)
                    resultado.falhas += 1
                    await sessao.rollback()
                    break
                anteriores = []
                await sessao.commit()
        total_fatos: dict[UUID, int] = {}
        for cid in fatos_por_contato:
            total_fatos[cid] = (
                await sessao.scalar(
                    select(func.count())
                    .select_from(FatoCliente)
                    .where(FatoCliente.contato_id == cid, FatoCliente.usuario_id == usuario_id)
                )
                or 0
            )
    for cid, novos in fatos_por_contato.items():
        if novos:
            await publicar(
                redis,
                ClienteAtualizado(
                    contato_id=cid,
                    canal=contatos[cid].canal,
                    novos_fatos=novos,
                    total_fatos=total_fatos.get(cid, 0),
                ),
                usuario_id,
            )
    if resultado.conhecimento_novo or resultado.conhecimento_atualizado:
        await publicar(
            redis,
            ConhecimentoAtualizado(
                motivo="leitura",
                itens_novos=resultado.conhecimento_novo,
                itens_atualizados=resultado.conhecimento_atualizado,
            ),
            usuario_id,
        )
    return resultado


async def _processar_pedaco(
    sessao: Any,
    usuario_id: UUID,
    extrator: Extrator,
    janela: list[MensagemEmpresa],
    pendentes: list[MensagemEmpresa],
    contatos: dict[UUID, ContatoEmpresa],
    resultado: ResultadoDaPassada,
    fatos_por_contato: dict[UUID, int],
) -> None:
    contatos_extra = {m.contato_id for m in janela} - set(contatos)
    if contatos_extra:
        for c in (
            await sessao.scalars(
                select(ContatoEmpresa).where(
                    ContatoEmpresa.id.in_(contatos_extra), ContatoEmpresa.usuario_id == usuario_id
                )
            )
        ).all():
            contatos[c.id] = c
    apelidos_cliente: dict[UUID, str] = {}
    apelidos_staff: dict[UUID, str] = {}
    para_extrair: list[MensagemParaExtrair] = []
    por_indice: dict[int, MensagemEmpresa] = {}
    for indice, m in enumerate(janela, start=1):
        contato = contatos.get(m.contato_id)
        if contato is None or m.texto is None:
            continue
        if m.direcao == "saida":
            apelido = apelidos_staff.setdefault(
                m.contato_id if contato.papel == "funcionario" else UUID(int=0),
                f"F{len(apelidos_staff) + 1}",
            )
            papel = "funcionario"
        else:
            apelido = apelidos_cliente.setdefault(m.contato_id, f"C{len(apelidos_cliente) + 1}")
            papel = "cliente"
        para_extrair.append(
            MensagemParaExtrair(indice, apelido, papel, m.texto, str(m.id), m.enviada_em)
        )
        por_indice[indice] = m
    ids_dos_pendentes = {m.id for m in pendentes}
    if not any(por_indice[p.indice].id in ids_dos_pendentes for p in para_extrair):
        for m in pendentes:
            m.processada_em = datetime.now(UTC)
        return
    bruta = await extrator(para_extrair)
    nomes = [c.nome for c in contatos.values() if c.nome] + list(apelidos_cliente.values())
    extracao = sanear(bruta, nomes)
    contato_do_apelido = {a: cid for cid, a in apelidos_cliente.items()}

    existentes = {
        (f.contato_id, f.tipo, base.normalizar(f.texto))
        for f in (
            await sessao.scalars(
                select(FatoCliente).where(
                    FatoCliente.usuario_id == usuario_id,
                    FatoCliente.contato_id.in_(contato_do_apelido.values()),
                )
            )
        ).all()
    }
    for fato in extracao.fatos:
        cid = contato_do_apelido.get(fato.apelido)
        if cid is None or not fato.texto.strip():
            continue
        origem = por_indice.get(fato.mensagem_indice or -1)
        chave = (cid, fato.tipo, base.normalizar(fato.texto))
        if chave in existentes:
            continue
        existentes.add(chave)
        sessao.add(
            FatoCliente(
                usuario_id=usuario_id,
                contato_id=cid,
                tipo=fato.tipo,
                texto=fato.texto,
                data_referencia=fato.data,
                origem_canal=origem.canal_externo if origem else "",
                origem_mensagem_id=origem.id if origem else None,
                origem_externo_id=origem.id_externo if origem else None,
                origem_link=origem.link if origem else None,
            )
        )
        fatos_por_contato[cid] += 1
        resultado.fatos_novos += 1
    itens = []
    for c in extracao.conhecimento:
        origem = por_indice.get(c.mensagem_indice or -1) or pendentes[-1]
        itens.append(
            (
                c,
                {
                    "canal": contatos[origem.contato_id].canal,
                    "mensagem_id": str(origem.id),
                    "externo_id": origem.id_externo,
                    "link": origem.link,
                    "em": origem.enviada_em.astimezone(UTC).isoformat(),
                    "contato_id": str(origem.contato_id),
                },
                origem.enviada_em,
            )
        )
    novos, atualizados = await base.fundir(sessao, usuario_id, itens)
    resultado.conhecimento_novo += novos
    resultado.conhecimento_atualizado += atualizados
    resultado.mensagens += len(pendentes)
    agora = datetime.now(UTC)
    await sessao.execute(
        update(MensagemEmpresa)
        .where(MensagemEmpresa.id.in_([m.id for m in pendentes]))
        .values(processada_em=agora)
    )
    for m in pendentes:
        m.processada_em = agora
