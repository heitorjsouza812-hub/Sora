"""Isolamento dos testes unitários do ``backend/.env`` do desenvolvedor.

A configuração lê o ``.env`` local (``SORA_MODELO_FALSO=1``, ``APP_URL`` etc.) quando a variável
não está no ambiente, então um teste que remove uma variável acabava lendo a do arquivo. Aqui o
``.env`` deixa de existir para a ``Configuracao``; o teste que precisa de um valor o declara com
``monkeypatch``, igual em qualquer máquina e na CI.
"""

from __future__ import annotations

import pytest

from app.core.config import Configuracao, obter_configuracao


@pytest.fixture(autouse=True)
def _sem_env_local(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(Configuracao.model_config, "env_file", None)
    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()
