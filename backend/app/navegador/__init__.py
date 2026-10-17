"""Navegador por texto (fase 3, ferramentas ``navegador_*``): o agente navega e lê a página
como texto e uma lista de elementos clicáveis, sem screenshot e sem desktop.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``page-browser-session.ts``
(seletor de elementos interativos, papel e nome acessível, senha mascarada, ref inválida
recusada) e ``browser-tools.ts``. O Rakazo prefere este modo e só cai para o desktop
gráfico quando ele não basta; a Sora fica só com este modo (veja
``docs/referencias/rakazo.md``, "O que ficou de fora").

O Playwright é opcional (``uv sync --group navegador`` e ``playwright install chromium``).
Toda navegação e todo pedido da página passam pela proteção SSRF do ``ler_pagina``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ferramentas.base import ErroFerramenta

MAX_ELEMENTOS = 80
MAX_TEXTO_PAGINA = 8_000
MAX_NOME_ELEMENTO = 120
ATRIBUTO_REF = "data-sora-ref"

SELETOR_INTERATIVO = ",".join(
    [
        "a[href]",
        "button",
        "input",
        "select",
        "textarea",
        "summary",
        "[role='button']",
        "[role='link']",
        "[role='textbox']",
        "[role='checkbox']",
        "[role='radio']",
        "[role='combobox']",
        "[role='menuitem']",
        "[contenteditable='true']",
    ]
)

SCRIPT_SNAPSHOT = """
([seletor, atributo, geracao, maxElementos, maxTexto, maxNome]) => {
  for (const antigo of document.querySelectorAll('[' + atributo + ']')) {
    antigo.removeAttribute(atributo);
  }
  const papel = (el) => {
    const explicito = el.getAttribute('role');
    if (explicito) return explicito;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button' || tag === 'summary') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      const tipo = (el.type || 'text').toLowerCase();
      if (tipo === 'checkbox' || tipo === 'radio') return tipo;
      if (['submit', 'button', 'reset'].includes(tipo)) return 'button';
      return 'textbox';
    }
    return tag;
  };
  const nome = (el) => {
    const aria = (el.getAttribute('aria-label') || '').trim();
    if (aria) return aria;
    const rotulo = el.labels && el.labels[0] ? el.labels[0].textContent.trim() : '';
    if (rotulo) return rotulo;
    if (el.placeholder && el.placeholder.trim()) return el.placeholder.trim();
    const texto = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    if (texto) return texto.slice(0, maxNome);
    if (el.name) return el.name;
    return el.tagName.toLowerCase();
  };
  const valor = (el) => {
    if (el instanceof HTMLInputElement) {
      if (el.type === 'checkbox' || el.type === 'radio') {
        return el.checked ? 'marcado' : 'desmarcado';
      }
      if (el.type === 'password') return el.value ? '••••' : '';
      return el.value;
    }
    if (el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) return el.value;
    return null;
  };
  const visivel = (el) => {
    if (el instanceof HTMLInputElement && el.type === 'hidden') return false;
    if (el.getAttribute('aria-hidden') === 'true') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const elementos = [];
  let total = 0;
  for (const el of document.querySelectorAll(seletor)) {
    if (!visivel(el)) continue;
    total += 1;
    if (elementos.length >= maxElementos) continue;
    const ref = 'g' + geracao + 'e' + (elementos.length + 1);
    el.setAttribute(atributo, ref);
    elementos.push({
      ref, papel: papel(el), nome: nome(el), tag: el.tagName.toLowerCase(), valor: valor(el),
    });
  }
  const bruto = document.body ? document.body.innerText : '';
  const texto = bruto.replace(/\\n{3,}/g, '\\n\\n').slice(0, maxTexto);
  return {url: location.href, titulo: document.title, texto, elementos, total};
}
"""


@dataclass(slots=True)
class Elemento:
    ref: str
    papel: str
    nome: str
    tag: str
    valor: str | None = None


@dataclass(slots=True)
class Snapshot:
    url: str
    titulo: str
    texto: str
    elementos: list[Elemento] = field(default_factory=list)
    total: int = 0


def ler_snapshot(dados: dict[str, Any]) -> Snapshot:
    elementos = [
        Elemento(
            ref=str(e.get("ref")),
            papel=str(e.get("papel") or ""),
            nome=str(e.get("nome") or "")[:MAX_NOME_ELEMENTO],
            tag=str(e.get("tag") or ""),
            valor=None if e.get("valor") is None else str(e.get("valor")),
        )
        for e in dados.get("elementos") or []
    ][:MAX_ELEMENTOS]
    return Snapshot(
        url=str(dados.get("url") or ""),
        titulo=str(dados.get("titulo") or ""),
        texto=str(dados.get("texto") or "")[:MAX_TEXTO_PAGINA],
        elementos=elementos,
        total=int(dados.get("total") or len(elementos)),
    )


def formatar_snapshot(snapshot: Snapshot) -> str:
    """Texto que o modelo recebe (vai na cerca ``<dado_externo>``)."""
    linhas = [
        f"- {e.papel} {e.nome!r} [{e.ref}]" + (f" valor={e.valor!r}" if e.valor is not None else "")
        for e in snapshot.elementos
    ]
    if snapshot.total > len(snapshot.elementos):
        linhas.append(
            f"- … mais {snapshot.total - len(snapshot.elementos)} elementos (role a página)"
        )
    return (
        f"Página: {snapshot.titulo or '(sem título)'}\nEndereço: {snapshot.url}\n\n"
        f"Elementos:\n{chr(10).join(linhas) or '(nenhum elemento interativo)'}\n\n"
        f"Texto:\n{snapshot.texto}"
    )


_REF = re.compile(r"^g(\d+)e(\d+)$")


def conferir_ref(ref: str, geracao_atual: int) -> None:
    """Recusa ref de um snapshot antigo (a página pode ter mudado)."""
    casamento = _REF.match(ref or "")
    if not casamento:
        raise ErroFerramenta(f"Ref inválida: {ref!r}. Use navegador_ler e uma ref nova.")
    if int(casamento.group(1)) != geracao_atual:
        raise ErroFerramenta(
            "Essa ref é de uma leitura antiga da página. Use navegador_ler de novo."
        )


# ---------- ferramentas ----------


class NavegadorAbrir(BaseModel):
    """Abre um endereço e devolve o texto e os elementos da página."""

    url: str = Field(min_length=8, max_length=2_000)


class NavegadorLer(BaseModel):
    """Lê de novo a página atual (texto e elementos com refs novas)."""


class AcaoNavegador(BaseModel):
    tipo: Literal["clicar", "digitar", "selecionar", "tecla", "rolar"]
    ref: str | None = Field(default=None, description="Ref do elemento (de navegador_ler).")
    texto: str | None = Field(
        default=None, max_length=2_000, description="Para digitar/selecionar."
    )
    tecla: str | None = Field(default=None, max_length=30, description="Ex.: Enter, Tab.")


class NavegadorAgir(BaseModel):
    """Faz até 5 ações seguidas na página (clicar, digitar, selecionar, tecla, rolar)."""

    acoes: list[AcaoNavegador] = Field(min_length=1, max_length=5)


TECLAS_PERMITIDAS = frozenset(
    {
        "Enter",
        "Tab",
        "Escape",
        "ArrowDown",
        "ArrowUp",
        "ArrowLeft",
        "ArrowRight",
        "PageDown",
        "PageUp",
        "Home",
        "End",
        "Backspace",
        "Space",
    }
)


def validar_acao(acao: AcaoNavegador, geracao_atual: int) -> None:
    if acao.tipo in {"clicar", "digitar", "selecionar"}:
        if not acao.ref:
            raise ErroFerramenta(f"A ação {acao.tipo} precisa de 'ref'.")
        conferir_ref(acao.ref, geracao_atual)
    if acao.tipo in {"digitar", "selecionar"} and acao.texto is None:
        raise ErroFerramenta(f"A ação {acao.tipo} precisa de 'texto'.")
    if acao.tipo == "tecla" and acao.tecla not in TECLAS_PERMITIDAS:
        raise ErroFerramenta("Tecla não permitida.")
