"""Lista de programas bloqueados do PC: servidor e ponte (Rust) iguais, macros e DevTools fora.

A ponte (``app/src-tauri/src/pc/regras.rs``) é quem confere de verdade; o servidor recusa de novo.
As duas listas são escritas à mão em linguagens diferentes: este teste pega quando uma muda e a
outra não (antes, ctrl+shift+K estava só no servidor)."""

import re
from pathlib import Path

import pytest

from app.computador.pc_usuario import PROGRAMAS_BLOQUEADOS, tecla_proibida

REGRAS_RS = Path(__file__).resolve().parents[3] / "app" / "src-tauri" / "src" / "pc" / "regras.rs"


def _lista_da_ponte() -> set[str]:
    if not REGRAS_RS.exists():
        pytest.skip("app/src-tauri não está neste checkout")
    texto = REGRAS_RS.read_text(encoding="utf-8")
    bloco = re.search(r"PROGRAMAS_BLOQUEADOS: &\[&str\] = &\[(.*?)\n\];", texto, re.S)
    assert bloco
    sem_comentarios = re.sub(r"//[^\n]*", "", bloco.group(1))
    return set(re.findall(r'"([^"]+)"', sem_comentarios))


def test_servidor_e_ponte_bloqueiam_os_mesmos_programas() -> None:
    ponte = _lista_da_ponte()
    assert ponte == set(PROGRAMAS_BLOQUEADOS), {
        "so_na_ponte": sorted(ponte - PROGRAMAS_BLOQUEADOS),
        "so_no_servidor": sorted(PROGRAMAS_BLOQUEADOS - ponte),
    }


@pytest.mark.parametrize(
    "programa", ["python.exe", "node.exe", "wmic.exe", "winget.exe", "reg.exe"]
)
def test_interpretadores_e_lolbins_bloqueados(programa: str) -> None:
    assert programa in PROGRAMAS_BLOQUEADOS


@pytest.mark.parametrize("tecla", ["alt+F11", "alt+F8", "ctrl+shift+k", "F12", "super+r"])
def test_atalhos_de_macro_e_devtools_proibidos(tecla: str) -> None:
    assert tecla_proibida(tecla)


@pytest.mark.parametrize("tecla", ["F11", "ctrl+s", "alt+F4", "F8"])
def test_atalhos_comuns_liberados(tecla: str) -> None:
    assert not tecla_proibida(tecla)
