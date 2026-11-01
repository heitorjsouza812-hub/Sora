"""Antes de agir: o elemento está pronto para receber a ação?

Checagens (cada uma ``passou``, ``falhou`` ou ``desconhecido``):

- **passageiras** (esperam até o prazo, conferindo a cada 100 ms): ``visivel``, ``estavel``
  (a posição não mudou entre dois quadros), ``habilitado``, ``recebe_eventos`` (algum dos 5
  pontos do elemento — centro e quadrantes — chega nele e não num elemento por cima);
- **definitivas** (falham na hora, esperar não resolve): ``suporta_acao``, ``politica``,
  ``editavel``.

``recebe_eventos`` só roda quando a ação vai pelo ponteiro, e falha **aberto**: sem evidência
(o ponto ficou fora da janela, por exemplo) o estado é ``desconhecido`` e a ação segue; só
falha com prova de que outro elemento está por cima, e então diz qual.

Ideia do agent-desktop (github.com/vercel-labs/agent-desktop, Apache-2.0): "actionability
battery", "auto-wait" e "occlusion gate". As regras e os nomes daqui são da Sora.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.navegador.arvore.resposta import Codigo, ErroNavegador

PRAZO_PADRAO_MS = 5_000
MS_POR_CARACTERE = 30
INTERVALO_MS = 100
TOLERANCIA_ESTAVEL_PX = 1.0


class Politica(StrEnum):
    """Como a ação pode chegar na página.

    - ``fisica`` (padrão da Sora): mouse e teclado do Playwright, eventos "de verdade"
      (``isTrusted``). O Chromium da Sora é isolado no servidor, então isso não rouba o mouse de
      ninguém.
    - ``semantica``: só pelo DOM (``element.click()``, ``value`` + evento ``input``). Não move o
      cursor do agente nem digita; gesto que só existe no físico (arrastar, passar o mouse,
      clique duplo) é recusado com ``POLITICA_NEGADA``.
    """

    FISICA = "fisica"
    SEMANTICA = "semantica"


class Status(StrEnum):
    PASSOU = "passou"
    FALHOU = "falhou"
    DESCONHECIDO = "desconhecido"


PASSAGEIRAS = frozenset({"visivel", "estavel", "habilitado", "recebe_eventos"})


@dataclass(frozen=True, slots=True)
class Checagem:
    nome: str
    status: Status
    motivo: str | None = None
    oclusor: dict[str, Any] | None = None

    def para_json(self) -> dict[str, Any]:
        saida: dict[str, Any] = {"checagem": self.nome, "status": self.status.value}
        if self.motivo:
            saida["motivo"] = self.motivo
        if self.oclusor:
            saida["oclusor"] = self.oclusor
        return saida


@dataclass(frozen=True, slots=True)
class Exigencia:
    """O que uma ação pede do elemento."""

    capacidade: str | None
    """Item do vocabulário de ações (``clicar``, ``editar``, ``marcar``…). ``None`` = qualquer."""
    ponteiro: bool = False
    edicao: bool = False
    so_fisica: bool = False
    habilitado: bool = True


@dataclass(slots=True)
class Relatorio:
    checagens: list[Checagem] = field(default_factory=list)
    ponto: tuple[int, int] | None = None

    @property
    def pronto(self) -> bool:
        return all(c.status is not Status.FALHOU for c in self.checagens)

    @property
    def falha_definitiva(self) -> Checagem | None:
        for c in self.checagens:
            if c.status is Status.FALHOU and c.nome not in PASSAGEIRAS:
                return c
        return None

    def primeira_falha(self) -> Checagem | None:
        return next((c for c in self.checagens if c.status is Status.FALHOU), None)

    def para_json(self) -> dict[str, Any]:
        return {"pronto": self.pronto, "checagens": [c.para_json() for c in self.checagens]}


def _estavel(antes: list[float] | None, depois: list[float] | None) -> bool:
    if not antes or not depois:
        return False
    return all(abs(a - b) <= TOLERANCIA_ESTAVEL_PX for a, b in zip(antes, depois, strict=True))


def avaliar(evidencia: dict[str, Any], exigencia: Exigencia, politica: Politica) -> Relatorio:
    """Transforma a evidência que a página juntou (``pagina.js``, ``evidencia``) no relatório."""
    rel = Relatorio()
    add = rel.checagens.append

    if exigencia.so_fisica and politica is Politica.SEMANTICA:
        add(Checagem("politica", Status.FALHOU, "esse gesto só existe com mouse/teclado"))
    else:
        add(Checagem("politica", Status.PASSOU))

    acoes = set(evidencia.get("acoes") or ())
    if exigencia.capacidade is None or exigencia.capacidade in acoes:
        add(Checagem("suporta_acao", Status.PASSOU))
    else:
        papel = evidencia.get("papel") or "elemento"
        add(Checagem("suporta_acao", Status.FALHOU, f"{papel} não aceita '{exigencia.capacidade}'"))

    visivel = bool(evidencia.get("visivel"))
    add(
        Checagem(
            "visivel",
            Status.PASSOU if visivel else Status.FALHOU,
            None if visivel else "elemento escondido ou sem tamanho",
        )
    )

    estavel = _estavel(evidencia.get("limites_antes"), evidencia.get("limites"))
    add(
        Checagem(
            "estavel",
            Status.PASSOU if estavel else Status.FALHOU,
            None if estavel else "elemento ainda se mexendo (animação ou carregamento)",
        )
    )

    if exigencia.habilitado:
        desabilitado = bool(evidencia.get("desabilitado"))
        add(
            Checagem(
                "habilitado",
                Status.FALHOU if desabilitado else Status.PASSOU,
                "elemento desabilitado" if desabilitado else None,
            )
        )

    if exigencia.edicao:
        editavel = bool(evidencia.get("editavel"))
        add(
            Checagem(
                "editavel",
                Status.PASSOU if editavel else Status.FALHOU,
                None if editavel else "campo somente leitura ou não editável",
            )
        )

    if exigencia.ponteiro and politica is Politica.FISICA:
        pontos = evidencia.get("pontos") or []
        acerto = next((p for p in pontos if p.get("acerta") is True), None)
        if acerto:
            rel.ponto = (int(acerto["x"]), int(acerto["y"]))
            add(Checagem("recebe_eventos", Status.PASSOU))
        else:
            tapado = next((p for p in pontos if p.get("acerta") is False), None)
            if tapado and len([p for p in pontos if p.get("acerta") is False]) == len(pontos):
                oclusor = tapado.get("oclusor") or {}
                add(
                    Checagem(
                        "recebe_eventos",
                        Status.FALHOU,
                        f"tapado por {oclusor.get('papel') or 'outro elemento'}",
                        oclusor=oclusor or None,
                    )
                )
            else:
                add(Checagem("recebe_eventos", Status.DESCONHECIDO, "sem ponto conferível na tela"))
    return rel


def erro_do_relatorio(rel: Relatorio, *, esgotou: bool, prazo_ms: int) -> ErroNavegador:
    """Erro para quando o elemento não ficou pronto. Nada foi enviado: repetir é seguro."""
    definitiva = rel.falha_definitiva
    detalhes = {"tipo": "acionabilidade", **rel.para_json()}
    if definitiva is not None:
        codigo = (
            Codigo.POLITICA_NEGADA
            if definitiva.nome == "politica"
            else (
                Codigo.ACAO_NAO_SUPORTADA
                if definitiva.nome == "suporta_acao"
                else Codigo.ACAO_FALHOU
            )
        )
        return ErroNavegador(codigo, definitiva.motivo or definitiva.nome, detalhes=detalhes)
    falha = rel.primeira_falha()
    motivo = falha.motivo if falha else "elemento não ficou pronto"
    if falha and falha.nome == "recebe_eventos":
        return ErroNavegador(
            Codigo.ACAO_FALHOU,
            f"O clique cairia em outro elemento: {motivo}.",
            detalhes=detalhes,
            sugestao="Feche o que está por cima (aviso de cookies, menu, diálogo) e tente de novo.",
        )
    detalhes["tipo"] = "acionabilidade_prazo" if esgotou else "acionabilidade"
    detalhes["prazo_ms"] = prazo_ms
    return ErroNavegador(
        Codigo.PRAZO_ESGOTADO, f"O elemento não ficou pronto: {motivo}.", detalhes=detalhes
    )


def prazo_para(acao: str, texto: str | None, prazo_ms: int | None) -> int:
    """Prazo padrão: 5 s; ``digitar`` ganha 30 ms por caractere. Um prazo explícito vence."""
    if prazo_ms is not None:
        return prazo_ms
    if acao == "digitar" and texto:
        return PRAZO_PADRAO_MS + MS_POR_CARACTERE * len(texto)
    return PRAZO_PADRAO_MS
