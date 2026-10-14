"""Dado de treino do Laya: gravação em ``roteamentos`` e rótulos.

Especificação: §7 "Quando entra" (fase 1: gravar dados de treino) e "Como conseguir os rótulos".
Colunas novas de ``roteamentos``: ``rotulo`` (jsonb), ``fonte_rotulo``, ``laya_saida`` (jsonb) e
``laya_latencia_ms``. Rótulos vêm do Verificador (plano errado), do usuário (cancelou e
reescreveu, ou trocou de agente) e da equipe (revisão semanal; pedidos de risco todos).
Os 100 pedidos do teste do Sistema 1 nunca entram no treino.

A tabela é de ``app/modelos`` (Alicerce); aqui a sessão é recebida de fora.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel

from app.sistema1.esquemas import ModoTriagem, Risco, Superficie

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.sistema1.triagem import ResultadoTriagem


class FonteRotulo(StrEnum):
    VERIFICADOR = "verificador"
    USUARIO = "usuario"
    EQUIPE = "equipe"


class RotuloLaya(BaseModel):
    """Decisões corretas, quando conhecidas (tabela de perguntas da §7). Campo ``None`` = não
    rotulado."""

    modo: ModoTriagem | None = None
    risco: Risco | None = None
    superficie: Superficie | None = None
    dificuldade: int | None = None
    precisa_visao: bool | None = None
    precisa_ferramentas: bool | None = None
    precisa_contexto_longo: bool | None = None
    injecao: bool | None = None
    vale_guardar_na_memoria: bool | None = None


async def gravar_roteamento(
    sessao: AsyncSession,
    mensagem_id: UUID,
    resultado: ResultadoTriagem,
    confianca: float | None = None,
) -> UUID:
    """Insere a decisão do N1 em ``roteamentos`` (modelo, confiança, escalou, latência).

    Respeita a flag ``sistema1.gravar_dados_de_treino`` de ``flags.yaml``. Devolve o id.
    """
    raise NotImplementedError


async def registrar_rotulo(
    sessao: AsyncSession,
    roteamento_id: UUID,
    rotulo: RotuloLaya,
    fonte: FonteRotulo,
) -> None:
    """Grava ``rotulo`` e ``fonte_rotulo`` numa linha de ``roteamentos``."""
    raise NotImplementedError


async def exportar_rotulados(
    sessao: AsyncSession,
    *,
    limite: int | None = None,
) -> list[dict[str, object]]:
    """Exporta pedidos rotulados no formato do Laya (fase 2: estado + perguntas), separando por
    usuário. Nunca inclui os pedidos do conjunto de teste fixo."""
    raise NotImplementedError
