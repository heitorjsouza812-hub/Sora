"""Path traversal em ``escrever_arquivo`` e ``ler_anexo`` (revisão B6; especificação §4)."""

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ferramentas.arquivos import (
    CaminhoInseguro,
    caminho_do_anexo,
    caminho_na_cadeia,
    dentro_da_pasta,
    gravar_na_cadeia,
    pasta_da_cadeia,
    validar_nome_arquivo,
)
from app.ferramentas.escrever_arquivo import EscreverArquivo
from app.ferramentas.ler_anexo import LerAnexo

RECUSADOS = [
    "",
    "../segredo.txt",
    "..",
    "a..b.txt",
    "pasta/arquivo.txt",
    "/etc/passwd",
    "pasta\\arquivo.txt",
    "C:\\Windows\\win.ini",
    "C:arquivo.txt",
    "relatorio.md:fluxo",
    "nome\x00.txt",
    "linha\nnova.txt",
    ".env",
    ".bashrc",
    "CON",
    "con.txt",
    "Prn.md",
    "AUX",
    "NUL.txt",
    "COM1",
    "com9.log",
    "LPT1.txt",
    "CONIN$",
    "arquivo.txt.",
    "arquivo.txt ",
    " arquivo.txt",
    "a<b>.txt",
    "a|b.txt",
    "a?.txt",
    "a*.txt",
    'a".txt',
    "x" * 121,
]

ACEITOS = [
    "relatorio.md",
    "Relatório final.txt",
    "posts-semana_1.csv",
    "plano.v2.md",
    "CONTEXTO.md",  # começa com CON, mas não é CON
    "com10.txt",
    "nulo.txt",
    "x" * 120,
]


@pytest.mark.parametrize("nome", RECUSADOS, ids=repr)
def test_nome_recusado(nome: str) -> None:
    with pytest.raises(CaminhoInseguro):
        validar_nome_arquivo(nome)


@pytest.mark.parametrize("nome", ACEITOS, ids=repr)
def test_nome_aceito(nome: str) -> None:
    assert validar_nome_arquivo(nome) == nome


@pytest.mark.parametrize("nome", RECUSADOS, ids=repr)
def test_esquema_da_ferramenta_recusa(nome: str) -> None:
    with pytest.raises(ValidationError):
        EscreverArquivo(nome=nome, conteudo="x")


@pytest.mark.parametrize("nome", ACEITOS, ids=repr)
def test_esquema_da_ferramenta_aceita(nome: str) -> None:
    assert EscreverArquivo(nome=nome, conteudo="x").nome == nome


def test_ler_anexo_so_aceita_uuid() -> None:
    with pytest.raises(ValidationError):
        LerAnexo(anexo_id="../../etc/passwd")  # type: ignore[arg-type]


# ---------- caminho resolvido ----------


def test_caminho_fica_na_pasta_da_cadeia(tmp_path: Path) -> None:
    usuario, cadeia = uuid4(), uuid4()
    caminho = caminho_na_cadeia(tmp_path, usuario, cadeia, "relatorio.md")
    assert caminho.parent == pasta_da_cadeia(tmp_path, usuario, cadeia).resolve()


@pytest.mark.parametrize(
    "relativo", ["../fora.txt", "../../fora.txt", ".", "", "sub/../../fora.txt"], ids=repr
)
def test_dentro_da_pasta_recusa_saida(tmp_path: Path, relativo: str) -> None:
    pasta = tmp_path / "cadeia"
    pasta.mkdir()
    with pytest.raises(CaminhoInseguro):
        dentro_da_pasta(pasta, pasta / relativo)


def test_dentro_da_pasta_recusa_caminho_absoluto(tmp_path: Path) -> None:
    pasta = tmp_path / "cadeia"
    pasta.mkdir()
    with pytest.raises(CaminhoInseguro):
        dentro_da_pasta(pasta, pasta / str(tmp_path / "outra" / "x.txt"))


def test_grava_dentro_da_pasta(tmp_path: Path) -> None:
    usuario, cadeia = uuid4(), uuid4()
    destino = gravar_na_cadeia(tmp_path, usuario, cadeia, "texto.md", "olá\nmundo")
    assert destino.read_text(encoding="utf-8") == "olá\nmundo"
    assert destino.is_relative_to(pasta_da_cadeia(tmp_path, usuario, cadeia).resolve())


def test_gravar_recusa_nome_inseguro_antes_de_criar_nada(tmp_path: Path) -> None:
    with pytest.raises(CaminhoInseguro):
        gravar_na_cadeia(tmp_path, uuid4(), uuid4(), "../fora.txt", "x")
    assert list(tmp_path.iterdir()) == []


def _criar_link(origem: Path, alvo: Path, *, pasta: bool) -> None:
    try:
        origem.symlink_to(alvo, target_is_directory=pasta)
    except OSError:
        pytest.skip("Sem permissão para criar link simbólico neste sistema")


def test_gravar_recusa_arquivo_que_e_link_para_fora(tmp_path: Path) -> None:
    usuario, cadeia = uuid4(), uuid4()
    fora = tmp_path / "fora.txt"
    fora.write_text("original", encoding="utf-8")
    pasta = pasta_da_cadeia(tmp_path / "volume", usuario, cadeia)
    pasta.mkdir(parents=True)
    _criar_link(pasta / "texto.md", fora, pasta=False)

    with pytest.raises(CaminhoInseguro):
        gravar_na_cadeia(tmp_path / "volume", usuario, cadeia, "texto.md", "x")
    assert fora.read_text(encoding="utf-8") == "original"


def test_gravar_recusa_pasta_da_cadeia_que_e_link_para_fora(tmp_path: Path) -> None:
    usuario, cadeia = uuid4(), uuid4()
    fora = tmp_path / "fora"
    fora.mkdir()
    pasta = pasta_da_cadeia(tmp_path / "volume", usuario, cadeia)
    pasta.parent.mkdir(parents=True)
    _criar_link(pasta, fora, pasta=True)

    # a pasta da cadeia aponta para fora: a conferência contra a raiz do volume pega
    with pytest.raises(CaminhoInseguro):
        gravar_na_cadeia(tmp_path / "volume", usuario, cadeia, "texto.md", "x")
    assert list(fora.iterdir()) == []


# ---------- ler_anexo ----------


def test_caminho_do_anexo_dentro_do_volume(tmp_path: Path) -> None:
    salvo = f"{uuid4()}/anexos/foto.png"
    assert caminho_do_anexo(tmp_path, salvo) == (tmp_path / salvo).resolve()


@pytest.mark.parametrize(
    "salvo",
    ["../segredo", "../../etc/passwd", "a/../../fora", "C:/Windows/win.ini", "/etc/passwd"],
    ids=repr,
)
def test_caminho_do_anexo_adulterado_e_recusado(tmp_path: Path, salvo: str) -> None:
    if salvo.startswith("C:") and sys.platform != "win32":
        salvo = "/etc/passwd"
    with pytest.raises(CaminhoInseguro):
        caminho_do_anexo(tmp_path, salvo)


def test_arquivo_gravado_so_para_o_dono_no_unix(tmp_path: Path) -> None:
    destino = gravar_na_cadeia(tmp_path, uuid4(), uuid4(), "a.txt", "x")
    if os.name == "posix":
        assert destino.stat().st_mode & 0o077 == 0
