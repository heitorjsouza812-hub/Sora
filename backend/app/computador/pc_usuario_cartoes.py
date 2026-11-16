"""Cartões "Precisa de você" do alvo ``pc_usuario`` (C3), no sistema de aprovações que já existe.

Dois assuntos, sempre um cartão por bot e assunto (``CanalPc.cartao``):

- **primeira ação num programa**: ``acao = {tipo: "pc_programa", ferramenta:
  "computador_pc_programa", argumentos/condicao: {programa}}``. "Sempre permitir" cria, pela rota
  de decisão de sempre (``api/aprovacoes.py``), uma ``regras_permissao`` com
  ``condicao.programa``; "Permitir uma vez" libera o programa para este trabalho
  (``CanalPc.permitir_uma_vez``). A regra vale só para o programa exato, nunca para o PC inteiro.
- **retomar depois da pausa** (o usuário mexeu no mouse ou no teclado): ``tipo: "pc_retomar"``,
  sem ferramenta (não existe "sempre" aqui). Permitir = o bot retoma; Recusar = Parar.

Ligado ao turno (Vela-12): o cartão nasce sem conversa (a ponte abre o de "retomar" pela rota
``/pausar``, entre um comando e outro). Quando o bot esbarra nele, ``vincular`` grava a etapa, o
grupo e ``acao.conversa_id`` **só se ainda estiver pendente** e o turno pausa (``interrupt`` do
LangGraph, como os cartões do revisor). A decisão, então, põe na fila a retomada daquele mesmo
turno (``api/aprovacoes.py``). Antes o bot esperava 90 s dentro da ferramenta e desistia: o
"Permitir" que chegava depois não retomava nada (teste do Heitor, 2026-11-15).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from app.computador.pc_usuario_canal import AgentePc

FERRAMENTA_PROGRAMA = "computador_pc_programa"
VALIDADE_CARTAO = timedelta(minutes=10)


class Cartoes(Protocol):
    async def agente(self, usuario_id: UUID, agente_id: UUID) -> AgentePc | None: ...

    async def abrir(
        self, usuario_id: UUID, agente_id: UUID, acao: dict[str, Any], motivo: str
    ) -> UUID: ...

    async def status(self, usuario_id: UUID, aprovacao_id: UUID) -> str | None:
        """``pendente`` · ``permitida`` · ``negada`` · ``expirada`` · ``None`` (sumiu)."""
        ...

    async def programas_sempre(self, usuario_id: UUID, agente_id: UUID) -> set[str]: ...

    async def vincular(
        self,
        usuario_id: UUID,
        aprovacao_id: UUID,
        *,
        conversa_id: UUID,
        etapa_id: UUID | None,
        grupo_id: UUID | None,
    ) -> bool:
        """Liga o cartão pendente ao turno que vai pausar. ``False`` se já foi decidido (ou
        venceu) antes disso: aí o bot segue com a decisão, sem pausar."""
        ...


@dataclass(slots=True)
class CartoesBanco:
    """Implementação de verdade (banco do worker)."""

    async def agente(self, usuario_id: UUID, agente_id: UUID) -> AgentePc | None:
        from sqlalchemy import select

        from app.ferramentas.infra import abrir_sessao
        from app.modelos.tabelas import Agente

        async with abrir_sessao() as sessao:
            linha = (
                await sessao.execute(
                    select(Agente.nome, Agente.cor).where(
                        Agente.id == agente_id,
                        Agente.usuario_id == usuario_id,
                        Agente.apagado_em.is_(None),
                    )
                )
            ).first()
        if linha is None:
            return None
        return AgentePc(id=agente_id, nome=str(linha[0])[:60], cor=str(linha[1] or "#E2ECFF"))

    async def abrir(
        self, usuario_id: UUID, agente_id: UUID, acao: dict[str, Any], motivo: str
    ) -> UUID:
        from app.atencao import publicar_estado_atencao_persistido
        from app.ferramentas.infra import abrir_sessao
        from app.modelos.enumeracoes import StatusAprovacao
        from app.modelos.tabelas import Aprovacao

        async with abrir_sessao() as sessao:
            cartao = Aprovacao(
                usuario_id=usuario_id,
                etapa_id=None,
                agente_id=agente_id,
                grupo_id=None,
                acao=acao,
                avaliacao={"modelo_revisor": False, "dano": "medio", "motivo": motivo},
                status=StatusAprovacao.PENDENTE,
                expira_em=datetime.now(UTC) + VALIDADE_CARTAO,
            )
            sessao.add(cartao)
            await sessao.flush()
            aprovacao_id = cartao.id
        await publicar_estado_atencao_persistido(usuario_id, agente_id=agente_id, grupo_id=None)
        return aprovacao_id

    async def vincular(
        self,
        usuario_id: UUID,
        aprovacao_id: UUID,
        *,
        conversa_id: UUID,
        etapa_id: UUID | None,
        grupo_id: UUID | None,
    ) -> bool:
        from sqlalchemy import func, update

        from app.ferramentas.infra import abrir_sessao
        from app.modelos.enumeracoes import StatusAprovacao
        from app.modelos.tabelas import Aprovacao

        async with abrir_sessao() as sessao:
            # Uma linha só e só pendente: a rota de decisão trava a mesma linha (FOR UPDATE), então
            # ou a decisão vem antes (aqui não muda nada e o bot segue) ou depois (já com o turno).
            resultado = await sessao.execute(
                update(Aprovacao)
                .where(
                    Aprovacao.id == aprovacao_id,
                    Aprovacao.usuario_id == usuario_id,
                    Aprovacao.status == StatusAprovacao.PENDENTE,
                    Aprovacao.expira_em > func.now(),
                )
                .values(
                    etapa_id=etapa_id,
                    grupo_id=grupo_id,
                    acao=Aprovacao.acao.op("||")(
                        func.jsonb_build_object("conversa_id", str(conversa_id))
                    ),
                )
            )
            return bool(resultado.rowcount)

    async def status(self, usuario_id: UUID, aprovacao_id: UUID) -> str | None:
        from sqlalchemy import select

        from app.ferramentas.infra import abrir_sessao
        from app.modelos.tabelas import Aprovacao

        async with abrir_sessao() as sessao:
            linha = (
                await sessao.execute(
                    select(Aprovacao.status, Aprovacao.expira_em).where(
                        Aprovacao.id == aprovacao_id, Aprovacao.usuario_id == usuario_id
                    )
                )
            ).first()
        if linha is None:
            return None
        status, expira_em = str(linha[0]), linha[1]
        if status == "pendente" and expira_em <= datetime.now(UTC):
            return "expirada"
        return status

    async def programas_sempre(self, usuario_id: UUID, agente_id: UUID) -> set[str]:
        from sqlalchemy import or_, select

        from app.ferramentas.infra import abrir_sessao
        from app.modelos.tabelas import RegraPermissao

        async with abrir_sessao() as sessao:
            condicoes = (
                await sessao.scalars(
                    select(RegraPermissao.condicao).where(
                        RegraPermissao.usuario_id == usuario_id,
                        RegraPermissao.ferramenta == FERRAMENTA_PROGRAMA,
                        or_(
                            RegraPermissao.agente_id.is_(None),
                            RegraPermissao.agente_id == agente_id,
                        ),
                    )
                )
            ).all()
        programas = set()
        for condicao in condicoes:
            programa = condicao.get("programa") if isinstance(condicao, dict) else None
            if isinstance(programa, str) and programa.strip():
                programas.add(programa.strip().lower())  # regra sem programa nunca libera tudo
        return programas
