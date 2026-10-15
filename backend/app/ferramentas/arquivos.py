"""Caminhos seguros no volume de arquivos (especificação §4: ``escrever_arquivo``
só na pasta da cadeia; §1, tabela ``anexos``).

Duas travas contra path traversal:

1. ``validar_nome_arquivo``: o nome vindo do modelo é só um nome de arquivo
   (sem pastas, sem ``..``, sem nomes reservados do Windows, sem começar com
   ponto). Usado pelo validador do esquema ``EscreverArquivo``.
2. ``dentro_da_pasta``: na hora de gravar ou ler, o caminho **resolvido**
   (links simbólicos seguidos) precisa ficar dentro da pasta esperada.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import UUID

MAX_NOME = 120

RESERVADOS_WINDOWS = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{n}" for n in "123456789¹²³"}
    | {f"LPT{n}" for n in "123456789¹²³"}
)
"""Nomes que o Windows trata como dispositivo, com ou sem extensão (``CON.txt``)."""

_PROIBIDOS = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')
"""Controle (inclui NUL), separadores de pasta, ``:`` (fluxo alternativo do NTFS)
e os caracteres que o Windows não aceita em nome de arquivo."""


class CaminhoInseguro(ValueError):
    """Nome ou caminho que sairia da pasta permitida."""


def validar_nome_arquivo(nome: str) -> str:
    """Devolve o nome se ele for seguro; senão levanta ``CaminhoInseguro``."""
    if not nome or len(nome) > MAX_NOME:
        raise CaminhoInseguro(f"O nome precisa ter de 1 a {MAX_NOME} caracteres.")
    if _PROIBIDOS.search(nome):
        raise CaminhoInseguro("O nome não pode ter pastas nem caracteres especiais.")
    if ".." in nome:
        raise CaminhoInseguro("O nome não pode ter '..'.")
    if nome.startswith("."):
        raise CaminhoInseguro("O nome não pode começar com ponto.")
    if nome != nome.strip() or nome.endswith("."):
        raise CaminhoInseguro(
            "O nome não pode começar ou terminar com espaço nem terminar com ponto."
        )
    if nome.split(".", 1)[0].strip().upper() in RESERVADOS_WINDOWS:
        raise CaminhoInseguro("Esse nome é reservado pelo sistema.")
    return nome


def dentro_da_pasta(pasta: Path, caminho: Path) -> Path:
    """Resolve ``caminho`` e confere que ele fica dentro de ``pasta``."""
    base = pasta.resolve()
    final = caminho.resolve()
    if final == base or not final.is_relative_to(base):
        raise CaminhoInseguro("O caminho sai da pasta permitida.")
    return final


def pasta_da_cadeia(raiz: Path, usuario_id: UUID, cadeia_id: UUID) -> Path:
    """``<raiz>/<usuario_id>/cadeias/<cadeia_id>``: a única pasta onde o Redator escreve."""
    return raiz / str(usuario_id) / "cadeias" / str(cadeia_id)


def caminho_na_cadeia(raiz: Path, usuario_id: UUID, cadeia_id: UUID, nome: str) -> Path:
    """Caminho final do arquivo, já validado (nome e destino resolvido).

    Confere contra a pasta da cadeia **e** contra a raiz do volume: se a pasta
    da cadeia (ou uma acima dela) virar link para fora, os dois lados da primeira
    conferência resolveriam pelo mesmo link e ela passaria sozinha.
    """
    pasta = pasta_da_cadeia(raiz, usuario_id, cadeia_id)
    destino = dentro_da_pasta(pasta, pasta / validar_nome_arquivo(nome))
    return dentro_da_pasta(raiz, destino)


def gravar_na_cadeia(
    raiz: Path, usuario_id: UUID, cadeia_id: UUID, nome: str, conteudo: str
) -> Path:
    """Grava o texto na pasta da cadeia e devolve o caminho. Síncrono: chamar com
    ``asyncio.to_thread``.

    Recusa sobrescrever um link simbólico (alguém trocando o arquivo por um link
    para fora da pasta entre a checagem e a escrita).
    """
    destino = caminho_na_cadeia(raiz, usuario_id, cadeia_id, nome)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino = caminho_na_cadeia(raiz, usuario_id, cadeia_id, nome)  # de novo, já com a pasta criada
    if destino.is_symlink():
        raise CaminhoInseguro("O destino é um link simbólico.")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    descritor = os.open(destino, flags, 0o600)
    with os.fdopen(descritor, "w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(conteudo)
    return destino


def caminho_do_anexo(raiz: Path, caminho_salvo: str) -> Path:
    """Caminho de um anexo lido do banco, conferido dentro do volume de arquivos.

    ``anexos.caminho`` é gravado pelo backend, mas a leitura confere de novo
    (defesa em profundidade contra um valor adulterado no banco).
    """
    return dentro_da_pasta(raiz, raiz / caminho_salvo)
