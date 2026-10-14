"""Catálogo de modelos: carrega ``config/catalogo_modelos.yaml``.

Especificação: §5 "Catálogo de modelos". Diz nível, capacidades, contexto, preço e velocidade de
cada modelo conhecido. Preço e contexto que faltarem no YAML vêm do ``litellm.model_cost``.
Modelo fora do catálogo entra como N2 e sem capacidades confirmadas, até ser testado ou
classificado pelo usuário. Modelos do OpenRouter são cruzados pelo nome sem o prefixo
``openrouter/``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

from app.seletor.tipos import Capacidade, NivelDeModelo


class EntradaCatalogo(BaseModel):
    modelo: str  # nome no LiteLLM
    provedor: str  # origem: groq, openai, anthropic, google, xai, deepseek, zai, mistral, ollama
    nivel: NivelDeModelo
    capacidades: list[Capacidade] = Field(default_factory=list)
    uso: str = ""
    contexto: int | None = None
    preco_entrada: Decimal | None = None  # US$ por 1M tokens
    preco_saida: Decimal | None = None
    velocidade_tps: int | None = None
    observacao: str | None = None
    confirmar_nome: bool = False
    somente_se_escolhido: bool = False  # ex.: claude-fable-5-1 nunca é escolhido sozinho


class ClassificacaoModelo(BaseModel):
    """Resultado do cruzamento de um modelo listado pelo provedor com o catálogo."""

    modelo: str
    nivel: NivelDeModelo
    capacidades: list[Capacidade]
    contexto: int
    preco_entrada: Decimal | None
    preco_saida: Decimal | None
    velocidade_tps: int | None
    origem: str  # "catalogo" ou "usuario" (valores de modelos_disponiveis.origem)


class Catalogo(BaseModel):
    versao: int
    conferido_em: date
    modelos: list[EntradaCatalogo]

    def buscar(self, nome_modelo: str) -> EntradaCatalogo | None:
        """Acha a entrada pelo nome no LiteLLM (aceita o prefixo ``openrouter/``)."""
        raise NotImplementedError

    def classificar(self, nome_modelo: str) -> ClassificacaoModelo:
        """Cruza o modelo com o catálogo, completando preço/contexto pelo LiteLLM.

        Fora do catálogo: N2, sem capacidades confirmadas, ``origem = "usuario"``.
        """
        raise NotImplementedError


def carregar_catalogo(caminho: Path | None = None) -> Catalogo:
    """Lê e valida o YAML."""
    raise NotImplementedError


def obter_catalogo() -> Catalogo:
    """O catálogo do processo (carregado uma vez, em cache)."""
    raise NotImplementedError
