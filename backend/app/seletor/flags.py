"""Flags: ligam e desligam recursos sem lançar versão (``config/flags.yaml``).

Especificação: §7 "Como ligar no Sistema 1" (uma flag desliga o Laya na hora) e plano 01
(tabela de tecnologias: Flags). Na fase 4 isto troca para o GrowthBook; quem usa só chama
``obter_flags()``, então a troca não muda os chamadores.
"""

from __future__ import annotations

from enum import StrEnum
from functools import cache
from pathlib import Path

from pydantic import BaseModel

from app.seletor.politica import diretorio_config, ler_yaml


class ModoLaya(StrEnum):
    DESLIGADO = "desligado"
    SOMBRA = "sombra"  # fase 2: decide em paralelo, quem manda é o N1
    LIGADO = "ligado"  # fase 3


class FlagsLaya(BaseModel):
    ativo: bool = False
    modo: ModoLaya = ModoLaya.DESLIGADO
    limite_confianca: float = 0.9
    prazo_ms: int = 150


class FlagsSistema1(BaseModel):
    gravar_dados_de_treino: bool = True


class FlagsRevisor(BaseModel):
    acoes_ativo: bool = False


class Flags(BaseModel):
    laya: FlagsLaya = FlagsLaya()
    sistema1: FlagsSistema1 = FlagsSistema1()
    revisor: FlagsRevisor = FlagsRevisor()


def carregar_flags(caminho: Path | None = None) -> Flags:
    """Lê e valida ``flags.yaml``. Arquivo vazio ou campos ausentes usam os padrões."""
    conteudo = ler_yaml(caminho or diretorio_config() / "flags.yaml")
    return Flags.model_validate(conteudo or {})


@cache
def obter_flags() -> Flags:
    """As flags do processo (carregadas uma vez; reiniciar o processo para reler)."""
    return carregar_flags()
