"""Planejador da cadeia (especificação §6, job ``planejar_cadeia``; prompt em
``prompts/planejador.v1.md``).

Roda no N3, uma vez por cadeia, com saída estruturada pelo LangChain (§6.1).
O backend valida o plano: no máximo 10 etapas, 5 especialistas e o
Verificador por último. Se faltar algo essencial, o planejador devolve uma
pergunta no lugar das etapas.
"""

from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modelos.enumeracoes import Nivel

Papel = Literal["pesquisador", "redator", "designer", "verificador"]


MAX_ETAPAS = 10
MAX_ESPECIALISTAS = 5


class EtapaPlano(BaseModel):
    """Uma etapa do plano, como o planejador devolve."""

    ordem: int = Field(ge=1)
    especialista: Papel
    nivel: Nivel
    tarefa: str
    pronto_quando: str
    depende_de: list[int] = Field(default_factory=list)


class Plano(BaseModel):
    """Plano completo; vai para ``cadeias.plano``."""

    objetivo: str
    requisitos: list[str]
    etapas: list[EtapaPlano] = Field(min_length=1, max_length=MAX_ETAPAS)


class PerguntaPlano(BaseModel):
    """Saída do planejador quando falta um dado essencial."""

    pergunta: str
    opcoes: list[str] = Field(min_length=2, max_length=4)


class PlanoInvalido(Exception):
    """O plano quebrou uma das regras de validação."""


def validar_plano(plano: Plano, *, tem_modelo_de_imagem: bool) -> None:
    """Confere as regras do plano: limites, Verificador por último, dependências
    válidas e Designer só com modelo de imagem. Levanta ``PlanoInvalido``."""
    ordens = [etapa.ordem for etapa in plano.etapas]
    if ordens != list(range(1, len(ordens) + 1)):
        raise PlanoInvalido("as etapas precisam ter ordens consecutivas a partir de 1")
    verificadores = [etapa for etapa in plano.etapas if etapa.especialista == "verificador"]
    if len(verificadores) != 1 or verificadores[0] is not plano.etapas[-1]:
        raise PlanoInvalido("o Verificador precisa ser a ultima e unica etapa de verificacao")
    especialistas = {
        etapa.especialista for etapa in plano.etapas if etapa.especialista != "verificador"
    }
    if len(especialistas) > MAX_ESPECIALISTAS:
        raise PlanoInvalido(f"o plano excede {MAX_ESPECIALISTAS} especialistas")
    if not tem_modelo_de_imagem and any(e.especialista == "designer" for e in plano.etapas):
        raise PlanoInvalido("Designer exige um modelo de imagem conectado")
    conhecidas: set[int] = set()
    for etapa in plano.etapas:
        if etapa.ordem in etapa.depende_de:
            raise PlanoInvalido(f"a etapa {etapa.ordem} depende dela mesma")
        if len(etapa.depende_de) != len(set(etapa.depende_de)):
            raise PlanoInvalido(f"a etapa {etapa.ordem} repete dependencias")
        ausentes = set(etapa.depende_de) - conhecidas
        if ausentes:
            lista = sorted(ausentes)
            raise PlanoInvalido(
                f"a etapa {etapa.ordem} depende de etapas futuras ou inexistentes: {lista}"
            )
        conhecidas.add(etapa.ordem)


def titulo_da_etapa(etapa: EtapaPlano) -> str:
    """Título curto mostrado no app ("Pesquisar referências"), vai para ``etapas.titulo``."""
    texto = re.sub(r"\s+", " ", etapa.tarefa).strip().rstrip(".?!")
    if not texto:
        return etapa.especialista.capitalize()
    titulo = " ".join(texto.split()[:6])
    if len(titulo) > 60:
        titulo = titulo[:57].rstrip() + "..."
    return titulo[0].upper() + titulo[1:]


async def planejar(cadeia_id: UUID) -> Plano | PerguntaPlano:
    """Chama o planejador para a cadeia e devolve o plano validado ou a pergunta."""
    raise NotImplementedError


async def gravar_plano(cadeia_id: UUID, plano: Plano) -> list[UUID]:
    """Grava o plano, cria as etapas e um especialista por papel (com aparência).

    Emite ``agente.criado`` para cada especialista e ``cadeia.criada``.
    Devolve os ids das etapas criadas.
    """
    raise NotImplementedError
