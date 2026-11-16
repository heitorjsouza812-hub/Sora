"""Peças comuns das ferramentas (especificação §4, "Regras de todas as ferramentas").

O contexto de cada chamada (quem chamou, em que etapa) e os limites comuns:
resultado acima de 20.000 caracteres vai para arquivo e cada chamada tem
prazo de 2 minutos.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

LIMITE_RESULTADO_CARACTERES = 20_000
PRAZO_FERRAMENTA_SEGUNDOS = 120
PRAZO_ETAPA_SEGUNDOS = 300


@dataclass(frozen=True, slots=True)
class ContextoFerramenta:
    """Quem está chamando a ferramenta. Nunca vem do modelo: o worker preenche."""

    usuario_id: UUID
    agente_id: UUID
    conversa_id: UUID
    cadeia_id: UUID | None = None
    etapa_id: UUID | None = None
    canal_id: UUID | None = None
    tarefa_canal_id: UUID | None = None
    revisao_canal: int | None = None
    sem_supervisao: bool = False
    """Rotina sem ninguém olhando: o navegador só usa abas efêmeras (sem login salvo)."""
    etapa_painel: UUID | None = None
    """Id sob o qual o painel Trabalho agrupa os passos deste turno (etapa ou turno da conversa
    direta). O passo "Aprovado automaticamente" sai com ele (Âncora-9)."""
    permissao: str | None = None
    """Modo de permissão fixo para esta execução; ``None`` = o da conversa (ou do bot)."""


class ErroFerramenta(Exception):
    """Erro que volta para o modelo como resultado da ferramenta (não derruba a etapa)."""
