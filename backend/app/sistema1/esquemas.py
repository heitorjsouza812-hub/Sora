"""Esquema da saída do Sistema 1 (JSON validado com Pydantic).

Fonte: ``docs/plano-de-implementacao/03-prompts.md`` ("Sistema 1: triagem e roteamento") e
especificação §5/§7. Numa conversa com agente individual, ``modo`` só pode ser ``direto`` ou
``cadeia`` (checado em ``triagem.py``).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ModoTriagem(StrEnum):
    DIRETO = "direto"
    CADEIA = "cadeia"
    AGENTE_INDIVIDUAL = "agente_individual"


class Especialista(StrEnum):
    PESQUISADOR = "pesquisador"
    REDATOR = "redator"
    DESIGNER = "designer"
    VERIFICADOR = "verificador"


class Superficie(StrEnum):
    MEMORIA = "memoria"
    CONECTOR = "conector"
    WEB = "web"
    NAVEGADOR = "navegador"
    NENHUMA = "nenhuma"


class Risco(StrEnum):
    NENHUM = "nenhum"
    ACAO_EXTERNA = "acao_externa"
    DESTRUTIVO = "destrutivo"


class CapacidadeTriagem(StrEnum):
    FERRAMENTAS = "ferramentas"
    VISAO = "visao"
    CONTEXTO_LONGO = "contexto_longo"
    IMAGEM = "imagem"


class SaidaSistema1(BaseModel):
    primeira_resposta: str
    modo: ModoTriagem
    resposta_direta: str | None = None  # só se modo = direto e dificuldade = 1
    dificuldade: Literal[1, 2, 3]
    especialistas: list[Especialista] = Field(default_factory=list, max_length=5)
    superficie: Superficie = Superficie.NENHUMA
    risco: Risco = Risco.NENHUM
    idioma: str  # BCP-47, ex.: pt-BR
    capacidades: list[CapacidadeTriagem] = Field(default_factory=list)
    agente_sugerido: str | None = None  # id de um agente individual
    confianca: float = Field(ge=0, le=1)
