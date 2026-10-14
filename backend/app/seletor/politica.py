"""Política do seletor: carrega e valida ``config/politica.yaml``.

Especificação: §5 "Arquivo politica.yaml". Papéis → nível, capacidades e preferências; dificuldade
→ nível; prioridade padrão; limites (confiança do Sistema 1, cadeia, especialistas, agentes
individuais, lembretes, pausa de provedor).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.modelos.enumeracoes import Nivel, Prioridade
from app.seletor.tipos import Capacidade, PapelModelo

VARIAVEL_DIRETORIO_CONFIG = "SORA_CONFIG_DIR"


class PoliticaPapel(BaseModel):
    nivel: Nivel | None = None  # o papel ``imagem`` não tem nível
    preferir: Prioridade | None = None
    capacidades: list[Capacidade] = Field(default_factory=list)
    subir_se_dificuldade: int | None = None  # resposta_direta
    diferente_do_executor: bool = False  # verificador
    diferente_de: PapelModelo | None = None  # memoria_verificacao
    preferir_modelo: str | None = None  # revisor


class LimitesCadeia(BaseModel):
    rodadas: int
    passos: int
    tokens: int


class Limites(BaseModel):
    confianca_minima_s1: float
    cadeia: LimitesCadeia
    especialistas_por_cadeia: int
    agentes_individuais_por_usuario: int
    lembrete_apos_chamadas_sem_falar: int
    falhas_para_pausar_provedor: int
    pausa_provedor_minutos: int


class Politica(BaseModel):
    papeis: dict[PapelModelo, PoliticaPapel]
    dificuldade_para_nivel: dict[int, Nivel]
    prioridade_padrao: Prioridade
    limites: Limites


def diretorio_config() -> Path:
    """``backend/config`` ou o valor de ``SORA_CONFIG_DIR``."""
    raise NotImplementedError


def carregar_politica(caminho: Path | None = None) -> Politica:
    """Lê e valida o YAML. Levanta erro claro se faltar papel ou o valor for inválido."""
    raise NotImplementedError


def obter_politica() -> Politica:
    """A política do processo (carregada uma vez, em cache)."""
    raise NotImplementedError
