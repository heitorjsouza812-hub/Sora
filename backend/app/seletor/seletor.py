"""``escolher_modelos``: o seletor de modelo (especificação §5, "Seletor de modelo").

Passos: (1) papel + dificuldade → nível pela política; (2) filtra modelos ativos com as
capacidades exigidas e contexto maior que o prompt; (3) tira provedores acima do teto ou em
pausa; (4) ordena pela prioridade do usuário; (5) devolve a lista (o 1º é usado, o resto é
reserva).

Regras: sem modelo no nível pedido sobe para o de cima, e se não houver usa o mais forte
disponível (e avisa); Sistema 1 usa o N1 mais rápido; verificador e verificação de memória
preferem outro provedor, senão outro modelo (e avisam se só houver um); conversa privada só com
Ollama; ``somente_se_escolhido`` nunca entra sozinho.

É função pura (sem banco, sem relógio global): tudo entra por ``ContextoSeletor``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.modelos.enumeracoes import Nivel, Prioridade
from app.seletor.politica import Politica
from app.seletor.tipos import (
    Capacidade,
    ContextoSeletor,
    ModeloCandidato,
    PapelModelo,
)


class TipoAviso(StrEnum):
    """Coisas que o seletor marca para a linha do tempo (§5)."""

    NIVEL_SUBIU = "nivel_subiu"
    USOU_O_MAIS_FORTE = "usou_o_mais_forte"
    VERIFICADOR_NO_MESMO_MODELO = "verificador_no_mesmo_modelo"
    VERIFICADOR_NO_MESMO_PROVEDOR = "verificador_no_mesmo_provedor"
    SEM_MODELO = "sem_modelo"


class AvisoSeletor(BaseModel):
    tipo: TipoAviso
    detalhe: str = ""


class ResultadoSelecao(BaseModel):
    """Lista ordenada de modelos (o 1º é usado) mais os avisos para a linha do tempo.

    Lista vazia = nada serve (ex.: nenhuma API conectada, ou conversa privada sem Ollama).
    """

    modelos: list[ModeloCandidato] = Field(default_factory=list)
    avisos: list[AvisoSeletor] = Field(default_factory=list)


def niveis_a_partir_de(nivel: Nivel) -> list[Nivel]:
    """N1 → [N1, N2, N3]; N2 → [N2, N3]; N3 → [N3]."""
    raise NotImplementedError


def ordenar(
    modelos: Sequence[ModeloCandidato],
    prioridade: Prioridade,
    preferir: Prioridade | None,
    preferir_modelo: str | None = None,
) -> list[ModeloCandidato]:
    """Ordena por custo, velocidade ou qualidade. ``preferir`` do papel vence a do usuário
    (ex.: Sistema 1 sempre por velocidade); ``preferir_modelo`` põe esse modelo na frente.
    """
    raise NotImplementedError


def escolher_modelos(
    contexto: ContextoSeletor,
    papel: PapelModelo,
    dificuldade: int,
    precisa: set[Capacidade],
    tokens_prompt: int,
    *,
    politica: Politica | None = None,
    agora: datetime | None = None,
    executor: ModeloCandidato | None = None,
    papel_irmao: ModeloCandidato | None = None,
) -> ResultadoSelecao:
    """Escolhe e ordena os modelos para uma chamada.

    ``executor`` é o modelo que fez o trabalho que o verificador vai conferir (papel
    ``verificador``); ``papel_irmao`` é o modelo da síntese de memória (papel
    ``memoria_verificacao``, ``diferente_de``). ``politica`` e ``agora`` existem para teste.
    """
    raise NotImplementedError
