"""Os controles de teste só existem com o modelo falso ligado."""

import subprocess
import sys

from app.core.config import obter_configuracao
from app.llm.falso import prazo_de_teste
from app.revisor.execucao import VALIDADE_DO_CARTAO


def test_prazo_do_cartao_so_muda_com_modelo_falso(monkeypatch):
    monkeypatch.setenv("SORA_PRAZO_APROVACAO_S", "3")
    try:
        monkeypatch.setenv("SORA_MODELO_FALSO", "0")
        obter_configuracao.cache_clear()
        assert prazo_de_teste("SORA_PRAZO_APROVACAO_S", VALIDADE_DO_CARTAO.total_seconds()) == 600

        monkeypatch.setenv("SORA_MODELO_FALSO", "1")
        obter_configuracao.cache_clear()
        assert prazo_de_teste("SORA_PRAZO_APROVACAO_S", VALIDADE_DO_CARTAO.total_seconds()) == 3
    finally:
        obter_configuracao.cache_clear()


def test_ferramenta_e_prazo_do_job_ignoram_gatilhos_sem_modelo_falso(monkeypatch):
    monkeypatch.setenv("SORA_MODELO_FALSO", "0")
    monkeypatch.setenv("SORA_PRAZO_JOB_S", "5")
    # Um processo novo lê as variáveis antes de importar WorkerSettings.
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
from uuid import uuid4

from app.ferramentas.base import ContextoFerramenta
from app.ferramentas.registro import criar_ferramentas
from app.revisor.politica import Politica, politica_da_ferramenta
from workers.configuracao import WorkerSettings

nome = "registrar_efeito_de_teste"
try:
    criar_ferramentas([nome], ContextoFerramenta(uuid4(), uuid4(), uuid4()))
except ValueError as erro:
    assert str(erro) == f"Ferramenta desconhecida: {nome}"
else:
    raise AssertionError("A ferramenta de teste foi criada com o modelo falso desligado")
assert politica_da_ferramenta(nome) is Politica.REVISOR
assert WorkerSettings.job_timeout == 360
""",
        ],
        check=True,
        timeout=30,
    )
