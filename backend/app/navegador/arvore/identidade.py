"""Reencontrar o elemento de uma ref antes de agir, sem chutar.

A página devolve candidatos em camadas (``pagina.js``, ``localizar``):

1. ``memoria`` — o mesmo objeto do DOM da leitura, se ainda está na página;
2. ``id`` — elementos com o mesmo id do HTML / ``data-testid`` / ``name``;
3. ``caminho`` — o elemento no mesmo caminho do DOM;
4. ``busca`` — todos os elementos visíveis com o mesmo papel (até um limite).

Cada camada só **localiza**; quem decide é a confirmação de identidade abaixo:

- o papel precisa ser o mesmo;
- se a ref e o candidato têm id nativo do mesmo tipo, os dois precisam ser iguais;
- se a ref tem nome estável (rótulo, não o valor digitado), o nome precisa bater;
- ref **sem identidade nenhuma** (sem id e sem nome) só se resolve pela posição, e só quando
  um único candidato ocupa o mesmo retângulo;
- na camada ``memoria`` o objeto é o mesmo, então basta o papel bater (o texto de um botão pode
  mudar, como "Seguir" → "Seguindo").

Um único candidato confirmado resolve. Mais de um → ``ALVO_AMBIGUO``. Nenhum em todas as
camadas → ``REF_VELHA``. Nunca se escolhe "o mais parecido".

Ideia do agent-desktop (github.com/vercel-labs/agent-desktop, Apache-2.0): "strict ref
resolution" e "graded resolution".
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from app.navegador.arvore.refs import EntradaRef
from app.navegador.arvore.resposta import Codigo, ErroNavegador

CAMADAS = ("memoria", "id", "caminho", "busca")
TOLERANCIA_POSICAO_PX = 2.0
MAX_CANDIDATOS_NO_ERRO = 5


def normalizar(texto: str | None) -> str:
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKC", texto)
    return " ".join(sem_acento.split()).casefold()


@dataclass(frozen=True, slots=True)
class Candidato:
    indice: int
    camada: str
    papel: str
    nome: str | None = None
    id_nativo: dict[str, str] | None = None
    limites: tuple[float, float, float, float] | None = None

    @classmethod
    def do_json(cls, dados: dict[str, Any], camada: str) -> Candidato:
        limites = dados.get("limites")
        return cls(
            indice=int(dados["indice"]),
            camada=camada,
            papel=str(dados.get("papel") or ""),
            nome=dados.get("nome") or None,
            id_nativo=dados.get("id_nativo") or None,
            limites=tuple(float(v) for v in limites) if limites else None,  # type: ignore[arg-type]
        )

    def resumo(self) -> dict[str, Any]:
        resumo: dict[str, Any] = {"papel": self.papel}
        if self.nome:
            resumo["nome"] = self.nome[:80]
        if self.limites:
            resumo["limites"] = [round(v) for v in self.limites]
        return resumo


def tem_identidade(entrada: EntradaRef) -> bool:
    return entrada.id_nativo is not None or bool(entrada.nome and entrada.nome_estavel)


def _mesmo_lugar(a: tuple[float, ...] | None, b: tuple[float, ...] | None) -> bool:
    if not a or not b or a[2] <= 0 or a[3] <= 0:
        return False
    return all(abs(x - y) <= TOLERANCIA_POSICAO_PX for x, y in zip(a, b, strict=True))


def confirma(entrada: EntradaRef, candidato: Candidato) -> bool:
    if candidato.papel != entrada.papel:
        return False
    if candidato.camada == "memoria":
        return True
    if entrada.id_nativo and candidato.id_nativo:
        if candidato.id_nativo.get("tipo") == entrada.id_nativo.tipo and (
            candidato.id_nativo.get("valor") != entrada.id_nativo.valor
        ):
            return False
    if entrada.nome and entrada.nome_estavel:
        return normalizar(candidato.nome) == normalizar(entrada.nome)
    if entrada.id_nativo:
        id_c = candidato.id_nativo or {}
        return id_c.get("tipo") == entrada.id_nativo.tipo and (
            id_c.get("valor") == entrada.id_nativo.valor
        )
    # sem identidade: só a posição exata decide
    return _mesmo_lugar(entrada.limites, candidato.limites)


@dataclass(frozen=True, slots=True)
class Resolucao:
    candidato: Candidato
    camada: str


def escolher(
    entrada: EntradaRef,
    ref: str,
    camadas: dict[str, list[Candidato]],
    memoria: str = "desconhecido",
) -> Resolucao:
    """Decide pelas camadas em ordem. Levanta ``REF_VELHA`` ou ``ALVO_AMBIGUO``.

    ``memoria`` diz o que houve com o objeto do DOM da leitura: ``vivo``, ``desconhecido``
    (página recarregada, objeto coletado) ou ``removido``. Removido é prova de que **aquele**
    elemento saiu da página: aí só o id do desenvolvedor pode reencontrá-lo; caminho e busca
    larga cairiam no vizinho que ocupou o lugar (a linha de baixo de uma lista, por exemplo).
    """
    permitidas = CAMADAS if memoria != "removido" else ("memoria", "id")
    for camada in permitidas:
        confirmados = [c for c in camadas.get(camada, []) if confirma(entrada, c)]
        if camada == "busca" and not tem_identidade(entrada):
            # sem identidade, a busca larga só serve se o lugar for único
            confirmados = [c for c in confirmados if _mesmo_lugar(entrada.limites, c.limites)]
        if len(confirmados) == 1:
            return Resolucao(confirmados[0], camada)
        if len(confirmados) > 1:
            raise ErroNavegador(
                Codigo.ALVO_AMBIGUO,
                f"{len(confirmados)} elementos da página batem com {ref}.",
                detalhes={
                    "ref": ref,
                    "camada": camada,
                    "candidatos": [c.resumo() for c in confirmados[:MAX_CANDIDATOS_NO_ERRO]],
                },
            )
    detalhes: dict[str, Any] = {"ref": ref, "papel": entrada.papel, "nome": entrada.nome}
    if memoria == "removido":
        detalhes["motivo"] = "elemento_removido"
    raise ErroNavegador(
        Codigo.REF_VELHA,
        f"{ref} não bate mais com nenhum elemento da página.",
        detalhes=detalhes,
    )
