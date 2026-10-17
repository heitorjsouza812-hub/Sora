"""Ferramenta ``catalogo_tarefas``: o inventário real do agente (ferramentas, habilidades,
agendamentos e pendências abertas).

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``task_catalog`` em
``adapters/src/builtin-tools.ts`` e ``task-catalog.ts``.

Serve para cortar alucinação de capacidade: o prompt manda chamar esta ferramenta antes de
afirmar que uma tarefa, rotina ou habilidade existe, e usar os ids e nomes exatos que ela
devolve, nunca o que "parece" pela conversa.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

DESCRICAO = (
    "Inventário somente leitura e fonte da verdade das ferramentas, habilidades, agendamentos e "
    "pendências abertas deste agente. Chame antes de dizer que uma tarefa ou habilidade existe. "
    "Use os ids e nomes exatos devolvidos; não deduza capacidades pela memória ou pela conversa."
)
INSTRUCAO_DE_USO = (
    "Antes de afirmar que você tem uma ferramenta, habilidade, agendamento ou pendência, confira "
    "com catalogo_tarefas e use os nomes e ids exatos que ele devolver."
)
MAX_ITENS_POR_SECAO = 50


class CatalogoTarefas(BaseModel):
    """Lista o que este agente realmente tem: ferramentas, habilidades, agenda e pendências."""


def montar_catalogo(
    *,
    ferramentas: Sequence[tuple[str, str]],
    habilidades: Sequence[tuple[str, str]] = (),
    agendamentos: Sequence[dict[str, Any]] = (),
    pendencias: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Junta o inventário. ``ferramentas`` e ``habilidades`` são ``(nome, descrição)``.

    Cada seção é cortada em 50 itens, com ``*_cortadas`` dizendo quantos ficaram de fora.
    """

    def secao(itens: Sequence[Any], nome: str) -> dict[str, Any]:
        lista = list(itens)
        saida: dict[str, Any] = {nome: lista[:MAX_ITENS_POR_SECAO]}
        if len(lista) > MAX_ITENS_POR_SECAO:
            saida[f"{nome}_cortadas"] = len(lista) - MAX_ITENS_POR_SECAO
        return saida

    return {
        **secao([{"nome": n, "descricao": d[:200]} for n, d in ferramentas], "ferramentas"),
        **secao([{"nome": n, "descricao": d[:200]} for n, d in habilidades], "habilidades"),
        **secao(list(agendamentos), "agendamentos"),
        **secao([p for p in pendencias if not p.get("concluida")], "pendencias_abertas"),
    }
