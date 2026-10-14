"""Postgres e Redis reais via Docker; sem Docker, todos os testes marcados são pulados."""

import shutil

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if shutil.which("docker"):
        return
    pular = pytest.mark.skip(reason="Docker não está instalado")
    for item in items:
        if "integracao" in item.keywords:
            item.add_marker(pular)
