"""Saída de processo com teto (``executar_comando`` e computador virtual).

Antes, ``capture_output=True`` guardava tudo na memória do worker: um ``yes`` no contêiner
derrubava o worker de todo mundo."""

import sys
import time

from app.computador import LIMITE_SAIDA_BYTES, ResultadoComando
from app.computador.processo import rodar_limitado

PY = [sys.executable, "-I", "-c"]


def test_saida_normal_passa_inteira() -> None:
    r = rodar_limitado([*PY, "print('oi'); import sys; sys.exit(3)"], prazo=30, limite_bytes=1000)
    assert r.codigo == 3 and r.stdout.strip() == b"oi"
    assert not r.cortado and not r.estourou_prazo


def test_saida_sem_fim_e_cortada_e_o_processo_morre() -> None:
    inicio = time.monotonic()
    r = rodar_limitado(
        [*PY, "import sys\nwhile True: sys.stdout.write('y' * 4096)"],
        prazo=60,
        limite_bytes=100_000,
    )
    assert r.cortado and not r.estourou_prazo
    assert len(r.stdout) == 100_000
    assert time.monotonic() - inicio < 20  # não esperou o prazo de 60 s


def test_erros_tambem_tem_teto() -> None:
    r = rodar_limitado(
        [*PY, "import sys\nwhile True: sys.stderr.write('e' * 4096)"],
        prazo=60,
        limite_bytes=50_000,
    )
    assert r.cortado and len(r.stderr) == 50_000


def test_prazo_estourado_mata_o_processo() -> None:
    inicio = time.monotonic()
    r = rodar_limitado([*PY, "import time; time.sleep(30)"], prazo=0.5, limite_bytes=1000)
    assert r.estourou_prazo and r.codigo is None
    assert time.monotonic() - inicio < 15


def test_entrada_chega_no_processo() -> None:
    r = rodar_limitado(
        [*PY, "import sys; sys.stdout.write(sys.stdin.read().upper())"],
        prazo=30,
        limite_bytes=1000,
        entrada=b"abc",
    )
    assert r.stdout == b"ABC"


def test_modelo_fica_sabendo_do_corte() -> None:
    texto = ResultadoComando(None, "y" * 10, "", cortado=True).para_modelo()
    assert f"{LIMITE_SAIDA_BYTES // 1024} KB" in texto and "interrompido" in texto
