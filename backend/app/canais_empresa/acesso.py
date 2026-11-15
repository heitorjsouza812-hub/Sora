"""Quem pode ver a ficha dos clientes e a base de conhecimento: só os bots e grupos que o
usuário autorizou (escopos ``clientes`` e ``conhecimento``). Sem autorização, ninguém vê.

Um bot dentro de um grupo autorizado vale como autorizado **naquele grupo**; no chat 1:1 ele
precisa da própria autorização.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canais_empresa.tabelas import AutorizacaoEmpresa
from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import Agente, CanalEquipe, MembroCanal

ESCOPOS = ("clientes", "conhecimento")
ALVOS = ("agente", "grupo")

SEM_AUTORIZACAO = (
    "Você não tem autorização para isso. O dono da conta libera em Configurações → Canais da "
    "empresa → Quem pode ver."
)


class ErroAcesso(ValueError):
    """Alvo inexistente ou de outra conta (a mensagem vai para o usuário)."""


async def autorizado(
    sessao: AsyncSession,
    usuario_id: UUID,
    escopo: str,
    *,
    agente_id: UUID,
    grupo_id: UUID | None = None,
) -> bool:
    condicoes = [
        (AutorizacaoEmpresa.alvo_tipo == "agente") & (AutorizacaoEmpresa.alvo_id == agente_id)
    ]
    if grupo_id is not None:
        condicoes.append(
            (AutorizacaoEmpresa.alvo_tipo == "grupo") & (AutorizacaoEmpresa.alvo_id == grupo_id)
        )
    achada = await sessao.scalar(
        select(AutorizacaoEmpresa.id)
        .where(
            AutorizacaoEmpresa.usuario_id == usuario_id,
            AutorizacaoEmpresa.escopo == escopo,
            or_(*condicoes),
        )
        .limit(1)
    )
    return achada is not None


async def listar(sessao: AsyncSession, usuario_id: UUID) -> list[AutorizacaoEmpresa]:
    return list(
        (
            await sessao.scalars(
                select(AutorizacaoEmpresa)
                .where(AutorizacaoEmpresa.usuario_id == usuario_id)
                .order_by(AutorizacaoEmpresa.criada_em, AutorizacaoEmpresa.id)
            )
        ).all()
    )


async def definir(
    sessao: AsyncSession,
    usuario_id: UUID,
    alvo_tipo: str,
    alvo_id: UUID,
    escopos: list[str],
) -> list[str]:
    """Troca os escopos autorizados de um bot ou grupo (lista vazia = tirar a autorização)."""
    if alvo_tipo not in ALVOS:
        raise ErroAcesso("Alvo inválido. Use agente ou grupo.")
    desconhecidos = set(escopos) - set(ESCOPOS)
    if desconhecidos:
        raise ErroAcesso("Escopo inválido: " + ", ".join(sorted(desconhecidos)) + ".")
    if alvo_tipo == "agente":
        existe = await sessao.scalar(
            select(Agente.id).where(
                Agente.id == alvo_id, Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None)
            )
        )
    else:
        existe = await sessao.scalar(
            select(CanalEquipe.id).where(
                CanalEquipe.id == alvo_id, CanalEquipe.usuario_id == usuario_id
            )
        )
    if existe is None:
        raise ErroAcesso("Bot ou grupo não encontrado.")
    await sessao.execute(
        delete(AutorizacaoEmpresa).where(
            AutorizacaoEmpresa.usuario_id == usuario_id,
            AutorizacaoEmpresa.alvo_tipo == alvo_tipo,
            AutorizacaoEmpresa.alvo_id == alvo_id,
        )
    )
    for escopo in dict.fromkeys(escopos):
        sessao.add(
            AutorizacaoEmpresa(
                usuario_id=usuario_id, alvo_tipo=alvo_tipo, alvo_id=alvo_id, escopo=escopo
            )
        )
    await sessao.flush()
    await sincronizar_ferramentas(sessao, usuario_id)
    return list(dict.fromkeys(escopos))


FERRAMENTA_DO_ESCOPO = {"clientes": "consultar_cliente", "conhecimento": "consultar_conhecimento"}


async def sincronizar_ferramentas(sessao: AsyncSession, usuario_id: UUID) -> None:
    """Dá a ferramenta de leitura aos bots autorizados (direto ou por grupo) e a tira dos que
    perderam a autorização. O acesso é conferido de novo a cada chamada da ferramenta."""
    por_escopo = {
        escopo: {b.id for b in await bots_com_escopo(sessao, usuario_id, escopo)}
        for escopo in ESCOPOS
    }
    donas = set(FERRAMENTA_DO_ESCOPO.values())
    agentes = (
        await sessao.scalars(
            select(Agente).where(
                Agente.usuario_id == usuario_id,
                Agente.apagado_em.is_(None),
                Agente.tipo != TipoAgente.SORA,
            )
        )
    ).all()
    for agente in agentes:
        atuais = list(agente.ferramentas or [])
        novas = [n for n in atuais if n not in donas]
        novas += [
            nome for escopo, nome in FERRAMENTA_DO_ESCOPO.items() if agente.id in por_escopo[escopo]
        ]
        if novas != atuais:
            agente.ferramentas = novas


async def bots_com_escopo(sessao: AsyncSession, usuario_id: UUID, escopo: str) -> list[Agente]:
    """Bots (nunca a Sora) autorizados direto ou por pertencerem a um grupo autorizado."""
    autorizacoes = [a for a in await listar(sessao, usuario_id) if a.escopo == escopo]
    ids = {a.alvo_id for a in autorizacoes if a.alvo_tipo == "agente"}
    grupos = [a.alvo_id for a in autorizacoes if a.alvo_tipo == "grupo"]
    if grupos:
        ids |= set(
            (
                await sessao.scalars(
                    select(MembroCanal.agente_id)
                    .join(CanalEquipe, CanalEquipe.id == MembroCanal.canal_id)
                    .where(
                        MembroCanal.canal_id.in_(grupos),
                        CanalEquipe.usuario_id == usuario_id,
                        CanalEquipe.arquivado_em.is_(None),
                    )
                )
            ).all()
        )
    if not ids:
        return []
    return list(
        (
            await sessao.scalars(
                select(Agente)
                .where(
                    Agente.id.in_(ids),
                    Agente.usuario_id == usuario_id,
                    Agente.apagado_em.is_(None),
                    Agente.tipo != TipoAgente.SORA,
                )
                .order_by(Agente.criado_em)
            )
        ).all()
    )
