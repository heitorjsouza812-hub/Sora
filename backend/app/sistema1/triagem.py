"""Chamada ao modelo N1 (triagem).

Especificação: §5 (Sistema 1 usa sempre o N1 mais rápido que o usuário conectou), §6.1 (chama o
modelo pelo LangChain, com saída estruturada) e prompts 03 (temperatura 0; não roda quando o
usuário escolheu "Agente independente"). O prompt vem de ``backend/prompts/`` (nunca no código).

Fluxo de ``triar``: regras → (Laya, fase 3) → N1 → validar; JSON inválido: um conserto; falhou:
reenvia ao N2 (``escalou = True``). O risco final é o maior entre regras, Laya e N1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.seletor.tipos import ContextoSeletor
from app.sistema1.esquemas import SaidaSistema1

if TYPE_CHECKING:
    from app.llm.provedores import ConfigProvedor

# Nome do prompt no registro de ``app/agentes/prompts.py`` (VERSOES): arquivo
# ``prompts/sistema1.v1.md``, carregado com ``carregar_prompt(PROMPT_SISTEMA1)``.
PROMPT_SISTEMA1 = "sistema1"


class AgenteIndividualResumo(BaseModel):
    id: str
    nome: str
    funcao: str


class ContextoTriagem(BaseModel):
    """Variáveis do prompt do Sistema 1."""

    agentes_individuais: list[AgenteIndividualResumo] = Field(default_factory=list)
    conectores: list[str] = Field(default_factory=list)
    ultimas_mensagens: list[str] = Field(default_factory=list)
    tem_modelo_de_imagem: bool = False
    em_conversa_com_agente: bool = False  # restringe modo a direto | cadeia


class ResultadoTriagem(BaseModel):
    """A decisão mais os dados que vão para ``roteamentos`` e para a linha do tempo."""

    saida: SaidaSistema1
    modelo: str
    latencia_ms: int
    escalou: bool = False  # True quando precisou do N2
    consertou: bool = False


def montar_prompt(pedido: str, contexto: ContextoTriagem) -> str:
    """Lê ``prompts/sistema1.v1.md`` e preenche as variáveis. O pedido entra como dado."""
    raise NotImplementedError


async def triar(
    pedido: str,
    contexto: ContextoTriagem,
    seletor: ContextoSeletor,
    provedores: dict[str, ConfigProvedor],
) -> ResultadoTriagem:
    """Triagem completa de um pedido. ``provedores`` mapeia ``provedor_id`` → chave decifrada
    (só na hora da chamada). Sem nenhum modelo servindo, levanta ``SemModeloDisponivel``.
    """
    raise NotImplementedError


class SemModeloDisponivel(Exception):
    """O seletor não achou modelo para o Sistema 1 (a API responde 412 antes de chegar aqui)."""
