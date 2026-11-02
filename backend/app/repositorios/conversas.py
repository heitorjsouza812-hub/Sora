"""Persistência de conversas e mensagens, sempre limitada ao dono."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.enumeracoes import AutorMensagem, StatusEtapa, TipoAgente, TipoConversa
from app.modelos.tabelas import (
    Agente,
    Anexo,
    Aprovacao,
    Cadeia,
    ChamadaModelo,
    Conversa,
    Entrega,
    Etapa,
    Mensagem,
    Passo,
    Pergunta,
    Reacao,
    RegistroAcao,
    Roteamento,
    Rotina,
)


async def listar(sessao: AsyncSession, usuario_id: UUID) -> list[Conversa]:
    consulta = (
        select(Conversa)
        .where(Conversa.usuario_id == usuario_id)
        .order_by(Conversa.atualizada_em.desc(), Conversa.id.desc())
    )
    return list((await sessao.scalars(consulta)).all())


async def obter(sessao: AsyncSession, usuario_id: UUID, conversa_id: UUID) -> Conversa | None:
    return await sessao.scalar(
        select(Conversa).where(
            Conversa.id == conversa_id,
            Conversa.usuario_id == usuario_id,
        )
    )


async def obter_agente(
    sessao: AsyncSession, usuario_id: UUID, agente_id: UUID | None
) -> Agente | None:
    consulta = select(Agente).where(
        Agente.usuario_id == usuario_id,
        Agente.apagado_em.is_(None),
    )
    if agente_id is None:
        consulta = consulta.where(Agente.tipo == TipoAgente.SORA)
    else:
        consulta = consulta.where(Agente.id == agente_id)
    return await sessao.scalar(consulta)


async def conferir_anexos(sessao: AsyncSession, usuario_id: UUID, anexos: list[UUID]) -> bool:
    if not anexos:
        return True
    encontrados = set(
        (
            await sessao.scalars(
                select(Anexo.id).where(Anexo.usuario_id == usuario_id, Anexo.id.in_(anexos))
            )
        ).all()
    )
    return encontrados == set(anexos)


async def criar(
    sessao: AsyncSession,
    *,
    usuario_id: UUID,
    agente: Agente,
    texto: str,
    anexos: list[UUID],
) -> tuple[Conversa, Mensagem]:
    tipo = TipoConversa.AGENTE if agente.tipo == TipoAgente.INDIVIDUAL else TipoConversa.CHAT
    conversa = Conversa(usuario_id=usuario_id, agente_id=agente.id, tipo=tipo)
    sessao.add(conversa)
    await sessao.flush()
    mensagem = await criar_mensagem(
        sessao,
        conversa=conversa,
        texto=texto,
        anexos=anexos,
    )
    return conversa, mensagem


async def criar_mensagem(
    sessao: AsyncSession,
    *,
    conversa: Conversa,
    texto: str,
    anexos: list[UUID],
    agente_id: UUID | None = None,
    autor: AutorMensagem = AutorMensagem.USUARIO,
) -> Mensagem:
    mensagem = Mensagem(
        conversa_id=conversa.id,
        autor=autor,
        agente_id=agente_id,
        conteudo=texto,
        anexos=[str(anexo) for anexo in anexos],
    )
    conversa.atualizada_em = datetime.now(UTC)
    sessao.add(mensagem)
    await sessao.flush()
    return mensagem


async def etapa_ativa_do_agente(
    sessao: AsyncSession,
    usuario_id: UUID,
    conversa_id: UUID,
    agente_id: UUID,
) -> Etapa | None:
    """Localiza a etapa que pode receber uma correção direta do usuário."""
    return await sessao.scalar(
        select(Etapa)
        .join(Cadeia, Cadeia.id == Etapa.cadeia_id)
        .where(
            Cadeia.usuario_id == usuario_id,
            Cadeia.conversa_id == conversa_id,
            Etapa.agente_id == agente_id,
            Etapa.status.in_(
                [
                    StatusEtapa.EXECUTANDO,
                    StatusEtapa.AGUARDANDO_USUARIO,
                    StatusEtapa.AGUARDANDO_APROVACAO,
                ]
            ),
        )
        .order_by(Etapa.iniciada_em.desc().nullslast(), Etapa.id.desc())
    )


async def renomear(
    sessao: AsyncSession, usuario_id: UUID, conversa_id: UUID, titulo: str
) -> Conversa | None:
    conversa = await obter(sessao, usuario_id, conversa_id)
    if conversa is None:
        return None
    conversa.titulo = titulo
    conversa.atualizada_em = datetime.now(UTC)
    await sessao.flush()
    return conversa


async def listar_mensagens(
    sessao: AsyncSession,
    usuario_id: UUID,
    conversa_id: UUID,
    *,
    antes: datetime | None,
    limite: int,
) -> list[Mensagem] | None:
    if await obter(sessao, usuario_id, conversa_id) is None:
        return None
    consulta = select(Mensagem).where(
        Mensagem.conversa_id == conversa_id,
        Mensagem.visivel.is_(True),
    )
    if antes is not None:
        consulta = consulta.where(Mensagem.criada_em < antes)
    consulta = consulta.order_by(Mensagem.criada_em.desc(), Mensagem.id.desc()).limit(limite)
    recentes = list((await sessao.scalars(consulta)).all())
    recentes.reverse()
    return recentes


async def apagar(
    sessao: AsyncSession,
    usuario_id: UUID,
    conversa_id: UUID,
    *,
    manter_agentes: bool,
) -> bool:
    """Apaga o agregado da conversa sem deixar FKs penduradas.

    Especialistas preservados viram agentes individuais; os demais recebem exclusão lógica,
    pois podem ter histórico em canais de equipe ou no correio.
    """
    conversa = await obter(sessao, usuario_id, conversa_id)
    if conversa is None:
        return False
    mensagens = list(
        (await sessao.scalars(select(Mensagem.id).where(Mensagem.conversa_id == conversa_id))).all()
    )
    cadeias = list(
        (await sessao.scalars(select(Cadeia.id).where(Cadeia.conversa_id == conversa_id))).all()
    )
    etapas = (
        list((await sessao.scalars(select(Etapa.id).where(Etapa.cadeia_id.in_(cadeias)))).all())
        if cadeias
        else []
    )
    especialistas = (
        list(
            (
                await sessao.scalars(
                    select(Agente.id).where(
                        Agente.usuario_id == usuario_id,
                        Agente.tipo == TipoAgente.ESPECIALISTA,
                        Agente.cadeia_id.in_(cadeias),
                    )
                )
            ).all()
        )
        if cadeias
        else []
    )
    if mensagens:
        await sessao.execute(delete(Reacao).where(Reacao.mensagem_id.in_(mensagens)))
        await sessao.execute(delete(Roteamento).where(Roteamento.mensagem_id.in_(mensagens)))
    await sessao.execute(
        update(Rotina).where(Rotina.conversa_id == conversa_id).values(conversa_id=None)
    )
    if etapas:
        await sessao.execute(delete(RegistroAcao).where(RegistroAcao.etapa_id.in_(etapas)))
        await sessao.execute(delete(Aprovacao).where(Aprovacao.etapa_id.in_(etapas)))
        await sessao.execute(delete(Passo).where(Passo.etapa_id.in_(etapas)))
    if cadeias:
        await sessao.execute(delete(ChamadaModelo).where(ChamadaModelo.cadeia_id.in_(cadeias)))
        await sessao.execute(delete(Entrega).where(Entrega.cadeia_id.in_(cadeias)))
        await sessao.execute(delete(Pergunta).where(Pergunta.cadeia_id.in_(cadeias)))
        await sessao.execute(delete(Etapa).where(Etapa.cadeia_id.in_(cadeias)))
    if especialistas:
        valores: dict[str, object] = {"cadeia_id": None}
        if manter_agentes:
            valores["tipo"] = TipoAgente.INDIVIDUAL
        else:
            valores["apagado_em"] = datetime.now(UTC)
        await sessao.execute(update(Agente).where(Agente.id.in_(especialistas)).values(**valores))
    if cadeias:
        await sessao.execute(delete(Cadeia).where(Cadeia.id.in_(cadeias)))
    await sessao.execute(delete(Pergunta).where(Pergunta.conversa_id == conversa_id))
    await sessao.execute(delete(Entrega).where(Entrega.conversa_id == conversa_id))
    await sessao.execute(delete(Mensagem).where(Mensagem.conversa_id == conversa_id))
    await sessao.delete(conversa)
    await sessao.flush()
    return True
