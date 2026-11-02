"""Aparência dos agentes no app (especificação §4, ``APARENCIA_POR_PAPEL``; §1,
colunas ``cor`` e ``movimento`` de ``agentes``).

Escolhida por código, nunca pelo modelo. Nomes e paleta são os mesmos do app
(``app/src/data/planejador.ts``: ``NOMES_AGENTES`` e ``PALETA_AGENTES``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.modelos.enumeracoes import Movimento

COR_SORA = "#E2ECFF"
"""Só a Sora usa esta cor."""

APARENCIA_POR_PAPEL: dict[str, dict[str, str]] = {
    "pesquisador": {"funcao": "Pesquisa e referências", "movimento": "vibracao"},
    "redator": {"funcao": "Textos e planejamento", "movimento": "ondas"},
    "designer": {"funcao": "Criação visual", "movimento": "espiral"},
    "verificador": {"funcao": "Verificação", "movimento": "gira"},
}

NOMES_AGENTES: tuple[str, ...] = (
    "Ravi", "Íris", "Caio", "Lia", "Téo", "Bia", "Davi", "Mel", "Noa", "Gael", "Zoe", "Leo",
    "Maya", "Cora", "Iara", "Tom", "Lis", "Rui", "Duda", "Juno", "Elis", "Otto", "Vera",
    "Ciro", "Nara", "Ian", "Ayla", "Enzo",
)  # fmt: skip

PALETA_AGENTES: tuple[str, ...] = (
    "#56A8FF",  # azul (Atlas)
    "#AC80FF",  # violeta (Luna)
    "#46E8A8",  # verde (Nina)
    "#FF8A5C",  # laranja
    "#FF6FAE",  # rosa
    "#FFD15C",  # âmbar
    "#4FD6E8",  # ciano
    "#A3E35A",  # lima
    "#FF6B6B",  # coral
    "#8C9BFF",  # índigo
    "#E89BFF",  # orquídea
    "#5CE0C6",  # turquesa
)


@dataclass(frozen=True, slots=True)
class Aparencia:
    nome: str
    funcao: str
    cor: str
    movimento: Movimento


def escolher_nome(em_uso: set[str]) -> str:
    """O primeiro nome livre de ``NOMES_AGENTES`` (nunca "Sora").

    Quando a lista acaba, repete os nomes com número ("Atlas 2"): nunca falha."""
    normalizados = {nome.casefold().strip() for nome in em_uso}
    for rodada in range(1, len(normalizados) + 2):
        for nome in NOMES_AGENTES:
            candidato = nome if rodada == 1 else f"{nome} {rodada}"
            if candidato.casefold() not in normalizados:
                return candidato
    raise AssertionError("inalcançável: há sempre um nome numerado livre")


def escolher_cor(em_uso: Iterable[str]) -> str:
    """A primeira cor livre de ``PALETA_AGENTES`` (nunca ``COR_SORA``).

    Quando a paleta acaba, reutiliza a que tem menos agentes (a primeira da paleta no empate):
    nunca falha e nunca devolve a cor da Sora. ``em_uso`` pode ser um ``set`` (cada cor conta
    uma vez) ou uma lista (conta repetições)."""
    usadas = [cor.upper() for cor in em_uso]
    for cor in PALETA_AGENTES:
        if cor.upper() not in usadas:
            return cor
    return min(PALETA_AGENTES, key=lambda cor: usadas.count(cor.upper()))


def aparencia_do_especialista(
    papel: str, nomes_em_uso: set[str], cores_em_uso: Iterable[str]
) -> Aparencia:
    """Aparência completa de um especialista novo na cadeia."""
    try:
        perfil = APARENCIA_POR_PAPEL[papel]
    except KeyError as erro:
        raise ValueError(f"Papel de especialista desconhecido: {papel!r}.") from erro
    return Aparencia(
        nome=escolher_nome(nomes_em_uso),
        funcao=perfil["funcao"],
        cor=escolher_cor(cores_em_uso),
        movimento=Movimento(perfil["movimento"]),
    )


def movimento_do_individual(funcao: str) -> Movimento:
    """Movimento de um agente individual criado a partir do pedido."""
    texto = funcao.casefold()
    if any(palavra in texto for palavra in ("pesquis", "dados", "analis")):
        return Movimento.VIBRACAO
    if any(palavra in texto for palavra in ("design", "visual", "imagem", "vídeo", "video")):
        return Movimento.ESPIRAL
    if any(palavra in texto for palavra in ("texto", "reda", "conteúdo", "conteudo", "planej")):
        return Movimento.ONDAS
    return Movimento.GIRA
