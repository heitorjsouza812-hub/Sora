"""Postgres e Redis reais via Docker; sem Docker utilizável, todos os testes marcados são pulados.

"Utilizável" = o daemon responde ao ``ping`` (VAL-01). Antes bastava o executável existir: com o
Docker instalado mas parado, a fixture ``servicos`` quebrava com ``DockerException`` (ERRO em vez
de skip).
"""

import shutil

import pytest


def docker_disponivel() -> tuple[bool, str]:
    """(pode rodar?, motivo para pular)."""
    if not shutil.which("docker"):
        return False, "Docker não está instalado"
    try:
        import docker

        cliente = docker.from_env()
        try:
            cliente.ping()
        finally:
            cliente.close()
    except Exception as erro:  # DockerException, conexão recusada, pipe ausente…
        return False, f"Docker não está respondendo ({type(erro).__name__})"
    return True, ""


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    marcados = [item for item in items if "integracao" in item.keywords]
    if not marcados:
        return
    disponivel, motivo = docker_disponivel()
    if disponivel:
        return
    pular = pytest.mark.skip(reason=motivo)
    for item in marcados:
        item.add_marker(pular)
