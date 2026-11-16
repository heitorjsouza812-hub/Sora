"""Teclado em editor local sem o juiz do revisor (C3, Vela-12).

``computador_agir`` passa pelo juiz do revisor (uma chamada ao modelo por ação) e, no PC do
usuário, nunca aceita "Sempre permitir". Preencher uma planilha custava uma chamada ao modelo a
mais por linha e, no plano grátis da Groq, gastava a cota do dia (teste do Heitor, 2026-11-15).

Regra: dispensa o juiz só quando **todas** as ações da chamada são digitar (texto sem cara de
senha), rolar ou uma tecla da lista curta de edição (Tab, Enter, setas, Esc, F2, ctrl+n/z/y…),
no alvo ``pc_usuario``. E então a ponte só aceita, nesta chamada, os **editores locais** (Excel,
Word, PowerPoint, Bloco de Notas, Paint, LibreOffice) que o usuário liberou no cartão do
programa: se a janela da frente for outra (navegador, e-mail), a ação é recusada e o bot volta a
passar pelo juiz. Clique e arrastar sempre passam pelo juiz. O cartão da primeira ação em cada
programa, a senha, os programas bloqueados, a pausa pelo mouse e o Parar continuam iguais.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

EDITORES_LOCAIS = frozenset(
    {"excel.exe", "winword.exe", "powerpnt.exe", "notepad.exe", "mspaint.exe", "soffice.bin"}
)

TECLAS_DE_EDICAO = frozenset(
    {
        "Tab",
        "shift+Tab",
        "Return",
        "shift+Return",
        "Escape",
        "Up",
        "Down",
        "Left",
        "Right",
        "Home",
        "End",
        "Page_Up",
        "Page_Down",
        "BackSpace",
        "Delete",
        "F2",
        "ctrl+n",
        "ctrl+z",
        "ctrl+y",
        "ctrl+Home",
        "ctrl+End",
    }
)

_SO_EDITORES: ContextVar[bool] = ContextVar("pc_so_editores_locais", default=False)


def dispensa_juiz(nome: str, argumentos: dict[str, Any]) -> bool:
    from app.computador.interface import normalizar_tecla, parece_senha
    from app.ferramentas.base import ErroFerramenta

    if nome != "computador_agir" or argumentos.get("alvo") != "pc_usuario":
        return False
    acoes = argumentos.get("acoes")
    if not isinstance(acoes, list) or not acoes:
        return False
    for acao in acoes:
        if not isinstance(acao, dict):
            return False
        tipo = acao.get("tipo")
        if tipo == "digitar":
            texto = acao.get("texto")
            if not isinstance(texto, str) or not texto or parece_senha(texto):
                return False
        elif tipo == "tecla":
            try:
                tecla = normalizar_tecla(str(acao.get("tecla") or ""))
            except ErroFerramenta:
                return False
            if tecla not in TECLAS_DE_EDICAO:
                return False
        elif tipo != "rolar" or acao.get("x") is not None:
            return False
    return True


def marcar(dispensado: bool) -> None:
    """O revisor marca, para esta chamada de ferramenta, se o juiz foi dispensado."""
    _SO_EDITORES.set(dispensado)


def programas_do_teclado_local() -> frozenset[str] | None:
    """Com o juiz dispensado, a ponte só aceita editores locais; senão, ``None`` (sem limite)."""
    return EDITORES_LOCAIS if _SO_EDITORES.get() else None
