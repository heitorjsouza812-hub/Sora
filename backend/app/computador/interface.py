"""Interface única ``Computador`` (C2/C3, ``docs/computador-por-bot.md``).

Um bot usa um computador por um dos alvos:

- ``virtual``: contêiner Linux só dele, com tela, navegador e arquivos (``virtual.py``);
- ``pc_usuario``: o PC do próprio usuário, pelo app de desktop (C3). Por enquanto só a
  interface e um stub que recusa (``pc_usuario.py``).

O ciclo é o mesmo do navegador por árvore (``docs/referencias/agent-desktop.md``): **observar**
(captura PNG + janelas e, quando o alvo tiver, árvore de acessibilidade) → **agir** (clicar,
digitar, tecla, rolar, arrastar) → **conferir** (nova observação e comparação com a anterior).
Quem conversa com o modelo é ``servico.py``; os alvos só sabem executar.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.ferramentas.base import ErroFerramenta

MAX_COORDENADA = 10_000
MAX_TEXTO_DIGITADO = 2_000
MAX_ACOES_POR_CHAMADA = 5
MAX_CAMINHO = 300


class Alvo(StrEnum):
    VIRTUAL = "virtual"
    PC_USUARIO = "pc_usuario"


@dataclass(frozen=True, slots=True)
class Tela:
    png: bytes
    largura: int
    altura: int

    @property
    def assinatura(self) -> str:
        """Muda quando qualquer pixel muda (usada na conferência depois de agir)."""
        return hashlib.sha256(self.png).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class Janela:
    id_nativo: str
    titulo: str
    x: int
    y: int
    largura: int
    altura: int
    ativa: bool = False
    programa: str | None = None

    @property
    def centro(self) -> tuple[int, int]:
        return self.x + self.largura // 2, self.y + self.altura // 2


@dataclass(frozen=True, slots=True)
class Observacao:
    tela: Tela
    janelas: list[Janela]
    arvore: list[dict[str, Any]] | None = None
    """Elementos de acessibilidade (C3 no Windows: UI Automation). O alvo virtual não tem."""


@dataclass(frozen=True, slots=True)
class ArquivoArea:
    caminho: str
    tipo: Literal["arquivo", "pasta", "outro"]
    tamanho: int


TipoAcao = Literal[
    "clicar",
    "clique_duplo",
    "clicar_direito",
    "digitar",
    "tecla",
    "rolar",
    "arrastar",
    "abrir",
]

Programa = Literal["navegador", "terminal"]


class AcaoComputador(BaseModel):
    """Uma ação de mouse ou teclado. Ponto por ``x``/``y`` (pixels da última captura) ou ``ref``
    de uma janela (``@cN:jM`` da última observação)."""

    tipo: TipoAcao
    x: int | None = Field(default=None, ge=0, le=MAX_COORDENADA)
    y: int | None = Field(default=None, ge=0, le=MAX_COORDENADA)
    ref: str | None = Field(default=None, max_length=40, description="Ref de janela (@cN:jM).")
    texto: str | None = Field(
        default=None, max_length=MAX_TEXTO_DIGITADO, description="Para digitar. Nunca senha."
    )
    tecla: str | None = Field(
        default=None, max_length=40, description="Ex.: Enter, Tab, ctrl+l, alt+tab."
    )
    direcao: Literal["cima", "baixo", "esquerda", "direita"] = "baixo"
    quantidade: int = Field(default=3, ge=1, le=15, description="Passos de rolagem.")
    ate_x: int | None = Field(default=None, ge=0, le=MAX_COORDENADA)
    ate_y: int | None = Field(default=None, ge=0, le=MAX_COORDENADA)
    programa: Programa | None = Field(default=None, description="Para abrir.")

    @model_validator(mode="after")
    def _coerente(self) -> AcaoComputador:
        tem_ponto = self.x is not None and self.y is not None
        if (self.x is None) != (self.y is None):
            raise ValueError("Informe x e y juntos.")
        if self.tipo in {"clicar", "clique_duplo", "clicar_direito"} and not (
            tem_ponto or self.ref
        ):
            raise ValueError(f"A ação {self.tipo} precisa de x/y ou de 'ref'.")
        if self.tipo == "digitar" and not self.texto:
            raise ValueError("A ação digitar precisa de 'texto'.")
        if self.tipo == "tecla" and not self.tecla:
            raise ValueError("A ação tecla precisa de 'tecla'.")
        if self.tipo == "arrastar" and not (
            tem_ponto and self.ate_x is not None and self.ate_y is not None
        ):
            raise ValueError("A ação arrastar precisa de x, y, ate_x e ate_y.")
        if self.tipo == "abrir" and self.programa is None:
            raise ValueError("A ação abrir precisa de 'programa' (navegador ou terminal).")
        return self


@dataclass(frozen=True, slots=True)
class AcaoResolvida:
    """Ação já conferida pelo serviço: ref virou janela, tecla virou combinação válida."""

    acao: AcaoComputador
    janela: Janela | None = None
    tecla: str | None = None
    ponto: tuple[int, int] | None = None


class Computador(Protocol):
    """O que todo alvo sabe fazer. Erros que o modelo deve ver são ``ErroFerramenta``."""

    alvo: Alvo

    async def observar(self) -> Observacao: ...

    async def agir(self, acao: AcaoResolvida) -> None: ...

    async def listar_arquivos(self, pasta: str) -> list[ArquivoArea]: ...

    async def ler_arquivo(self, caminho: str, limite: int) -> bytes: ...

    async def escrever_arquivo(self, caminho: str, dados: bytes) -> None: ...


class ProvedorComputadores(Protocol):
    """Entrega o computador de um bot (cria ou reaproveita)."""

    async def obter(self, usuario_id: UUID, agente_id: UUID) -> Computador: ...

    async def desligar(self, agente_id: UUID) -> bool: ...


# ---------- teclas ----------

_MODIFICADORES = {"ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift"}
_TECLAS = {
    "enter": "Return",
    "return": "Return",
    "tab": "Tab",
    "escape": "Escape",
    "esc": "Escape",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "space": "space",
    "espaco": "space",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "arrowup": "Up",
    "arrowdown": "Down",
    "arrowleft": "Left",
    "arrowright": "Right",
    "pageup": "Page_Up",
    "pagedown": "Page_Down",
    "home": "Home",
    "end": "End",
    **{f"f{n}": f"F{n}" for n in range(1, 13)},
}
_LETRA = re.compile(r"^[a-z0-9]$")
_PROIBIDAS = {frozenset({"ctrl", "alt", "delete"}), frozenset({"ctrl", "alt", "backspace"})}


def normalizar_tecla(texto: str) -> str:
    """``ctrl+L`` → ``ctrl+l``; ``Enter`` → ``Return``. Recusa o que não está na lista."""
    partes = [p.strip().lower() for p in texto.replace(" ", "").split("+") if p.strip()]
    if not partes or len(partes) > 4:
        raise ErroFerramenta("Tecla não permitida.")
    *mods, base = partes
    nomes_mods = []
    for mod in mods:
        if mod not in _MODIFICADORES:
            raise ErroFerramenta(f"Modificador não permitido: {mod}.")
        nomes_mods.append(_MODIFICADORES[mod])
    if base in _TECLAS:
        nome_base = _TECLAS[base]
    elif _LETRA.match(base) and nomes_mods:
        nome_base = base
    else:
        raise ErroFerramenta(
            "Tecla não permitida. Use Enter, Tab, Escape, setas, PageUp/PageDown, Home, End, "
            "Backspace, Delete, F1 a F12 ou combinações com ctrl/alt/shift (ex.: ctrl+l)."
        )
    if frozenset([*nomes_mods, nome_base.lower()]) in _PROIBIDAS:
        raise ErroFerramenta("Essa combinação de teclas não é permitida.")
    return "+".join([*dict.fromkeys(nomes_mods), nome_base])


# ---------- senha e segredo ----------

_CLASSES = (re.compile(r"[a-z]"), re.compile(r"[A-Z]"), re.compile(r"\d"), re.compile(r"[^\w\s]"))


def parece_senha(texto: str) -> bool:
    """Heurística: uma "palavra" só, de 8 a 128 caracteres, com 3 das 4 classes (minúscula,
    maiúscula, dígito, símbolo) e que não é endereço nem e-mail. Na dúvida, recusa digitar."""
    from app.core.redacao import limpar_texto_sensivel

    if limpar_texto_sensivel(texto) != texto:
        return True  # chave de API, token, JWT… (padrões da redação)
    palavra = texto.strip()
    if " " in palavra or not 8 <= len(palavra) <= 128:
        return False
    if (
        "://" in palavra
        or palavra.startswith("www.")
        or re.fullmatch(r"[^@\s]+@[^@\s]+\.\w+", palavra)
    ):
        return False
    return sum(1 for classe in _CLASSES if classe.search(palavra)) >= 3


# ---------- caminhos da área do bot ----------


def caminho_relativo(texto: str) -> str:
    """Caminho relativo à área do bot, sem ``..``, sem barra inicial e sem caractere de controle."""
    bruto = (texto or "").strip().replace("\\", "/")
    if not bruto or bruto in {".", "/"}:
        return ""
    if len(bruto) > MAX_CAMINHO or any(ord(c) < 32 for c in bruto):
        raise ErroFerramenta("Caminho inválido.")
    caminho = PurePosixPath(bruto)
    if caminho.is_absolute() or any(parte == ".." for parte in caminho.parts):
        raise ErroFerramenta("Use um caminho dentro da sua área de arquivos (sem '..' e sem '/').")
    return str(caminho)


# ---------- refs de janela ----------

_REF = re.compile(r"^@c(\d+):j(\d+)$")


@dataclass(slots=True)
class LeituraGuardada:
    geracao: int
    observacao: Observacao
    refs: dict[str, Janela] = field(default_factory=dict)


def ref_da_janela(geracao: int, indice: int) -> str:
    return f"@c{geracao}:j{indice}"


def ler_ref(ref: str) -> tuple[int, int]:
    achou = _REF.match(ref or "")
    if achou is None:
        raise ErroFerramenta(f"Ref inválida: {ref!r}. Use uma ref @cN:jM de computador_observar.")
    return int(achou.group(1)), int(achou.group(2))
