"""Tipos compartilhados do seletor: níveis, capacidades, papéis e candidatos.

Especificação: §5 (catálogo, política, esqueleto do seletor) e §1 (``provedores`` e
``modelos_disponiveis``). São tipos puros, sem banco: quem chama o seletor monta os candidatos a
partir das linhas do banco. Isso deixa ``escolher_modelos`` testável com tabelas de casos (§8.5).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modelos.enumeracoes import Nivel, Prioridade, TipoProvedor

NivelDeModelo = Nivel | Literal["especial"]
"""Nível de um modelo do catálogo: a escada N1 a N3 (enum central) ou ``especial`` (revisor,
detector de injeção, imagem, embeddings), que fica fora da escada."""


class Capacidade(StrEnum):
    """Valores de ``modelos_disponiveis.capacidades`` (§1); ``EMBEDDINGS`` é extensão nossa."""

    FERRAMENTAS = "ferramentas"
    JSON = "json"
    VISAO = "visao"
    IMAGEM = "imagem"
    EMBEDDINGS = "embeddings"


class PapelModelo(StrEnum):
    """Chaves de ``papeis`` em ``politica.yaml``."""

    SISTEMA1 = "sistema1"
    RESPOSTA_DIRETA = "resposta_direta"
    SORA = "sora"
    PLANEJADOR = "planejador"
    PESQUISADOR = "pesquisador"
    REDATOR = "redator"
    DESIGNER = "designer"
    IMAGEM = "imagem"
    AGENTE_INDIVIDUAL = "agente_individual"
    VERIFICADOR = "verificador"
    REVISOR = "revisor"
    MEMORIA_SINTESE = "memoria_sintese"
    MEMORIA_VERIFICACAO = "memoria_verificacao"


class ProvedorSeletor(BaseModel):
    """Estado do provedor do usuário no momento da escolha."""

    id: UUID
    tipo: TipoProvedor
    pausado_ate: datetime | None = None
    teto_mensal_usd: Decimal | None = None
    gasto_mes_usd: Decimal = Decimal(0)

    def em_pausa(self, agora: datetime) -> bool:
        """True enquanto ``pausado_ate`` ainda não passou (3 falhas seguidas, §5)."""
        return self.pausado_ate is not None and self.pausado_ate > agora

    def passou_do_teto(self) -> bool:
        """True quando o gasto do mês chegou ao teto mensal do provedor (sem teto = nunca)."""
        return self.teto_mensal_usd is not None and self.gasto_mes_usd >= self.teto_mensal_usd


class ModeloCandidato(BaseModel):
    """Uma linha de ``modelos_disponiveis`` já ligada ao seu provedor."""

    modelo: str  # nome no LiteLLM, ex.: groq/openai/gpt-oss-20b
    provedor: ProvedorSeletor
    nivel: NivelDeModelo
    capacidades: frozenset[Capacidade] = frozenset()
    contexto: int
    preco_entrada: Decimal | None = None  # US$ por 1M tokens
    preco_saida: Decimal | None = None
    velocidade_tps: int | None = None
    ativo: bool = True
    # Do catálogo (``EntradaCatalogo.somente_se_escolhido``): só entra se o usuário o escolheu.
    somente_se_escolhido: bool = False


class ContextoSeletor(BaseModel):
    """O que o seletor sabe do usuário (equivale ao ``usuario`` do esqueleto da §5)."""

    modelos: list[ModeloCandidato] = Field(default_factory=list)
    prioridade: Prioridade = Prioridade.CUSTO
    conversa_privada: bool = False  # privada = só modelos locais (Ollama)

    def modelos_ativos(self) -> list[ModeloCandidato]:
        return [modelo for modelo in self.modelos if modelo.ativo]
