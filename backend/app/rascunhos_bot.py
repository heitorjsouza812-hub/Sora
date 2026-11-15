"""Rascunhos persistentes de bots da etapa 5.

O rascunho não cria agente. A criação (e a rotina opcional) acontece somente na
confirmação, sob a mesma transação e com uso único.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentes.aparencia import escolher_cor, escolher_nome
from app.ferramentas.permissoes import FERRAMENTAS_POR_PAPEL
from app.modelos.tabelas import Agente, RascunhoBot, Usuario


class RotinaRascunhoBot(BaseModel):
    descricao: str = Field(min_length=1, max_length=4_000)
    agendamento: str = Field(min_length=1, max_length=120)
    fuso: str = Field(min_length=1, max_length=120)


class RascunhoBotSaida(BaseModel):
    id: UUID
    nome: str
    funcao: str
    cor: str
    instrucoes: str
    ferramentas: list[str]
    rotina: RotinaRascunhoBot | None
    status: Literal["rascunho"] = "rascunho"


class RascunhoBotAjuste(BaseModel):
    id: UUID | None = None
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    funcao: str | None = Field(default=None, min_length=1, max_length=2_000)
    cor: str | None = Field(default=None, max_length=32)
    instrucoes: str | None = Field(default=None, max_length=20_000)
    ferramentas: list[str] | None = Field(default=None, max_length=50)
    rotina: RotinaRascunhoBot | None = None


def saida_do_rascunho(rascunho: RascunhoBot) -> RascunhoBotSaida:
    return RascunhoBotSaida(id=rascunho.id, **rascunho.dados, status="rascunho")


async def dados_sugeridos(
    sessao: AsyncSession,
    usuario_id: UUID,
    *,
    descricao: str,
    nome: str | None = None,
    funcao: str | None = None,
) -> dict:
    agentes = list(
        await sessao.scalars(
            select(Agente).where(Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None))
        )
    )
    pendentes = list(
        await sessao.scalars(
            select(RascunhoBot).where(
                RascunhoBot.usuario_id == usuario_id, RascunhoBot.status == "rascunho"
            )
        )
    )
    nomes = {agente.nome for agente in agentes} | {r.dados["nome"] for r in pendentes}
    cores = [agente.cor for agente in agentes] + [r.dados["cor"] for r in pendentes]
    sugerido = (nome or "").strip()
    if not sugerido or sugerido.casefold() in {n.casefold() for n in nomes}:
        sugerido = escolher_nome(nomes)
    primeira = descricao.strip().splitlines()[0].strip().split(". ")[0].rstrip(".")
    return {
        "nome": sugerido,
        "funcao": (funcao or primeira[:80] or "Assistente especializado").strip(),
        "cor": escolher_cor(cores),
        "instrucoes": descricao.strip(),
        "ferramentas": list(FERRAMENTAS_POR_PAPEL["individual"]),
        "rotina": None,
    }


async def criar_rascunho(
    sessao: AsyncSession,
    usuario_id: UUID,
    *,
    descricao: str,
    conversa_id: UUID | None = None,
    nome: str | None = None,
    funcao: str | None = None,
) -> RascunhoBot:
    await sessao.scalar(select(Usuario.id).where(Usuario.id == usuario_id).with_for_update())
    rascunho = RascunhoBot(
        usuario_id=usuario_id,
        conversa_id=conversa_id,
        dados=await dados_sugeridos(
            sessao, usuario_id, descricao=descricao, nome=nome, funcao=funcao
        ),
    )
    sessao.add(rascunho)
    await sessao.flush()
    return rascunho


async def obter_rascunho_para_atualizar(
    sessao: AsyncSession, usuario_id: UUID, rascunho_id: UUID
) -> RascunhoBot | None:
    return await sessao.scalar(
        select(RascunhoBot)
        .where(RascunhoBot.id == rascunho_id, RascunhoBot.usuario_id == usuario_id)
        .with_for_update()
    )


def resolver(rascunho: RascunhoBot, status: Literal["confirmado", "descartado"]) -> None:
    rascunho.status = status
    rascunho.resolvido_em = datetime.now().astimezone()
