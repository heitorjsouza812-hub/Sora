"""Postgres e Redis reais via Docker; sem Docker utilizável, todos os testes marcados são pulados.

"Utilizável" = o daemon responde ao ``ping`` (VAL-01). Antes bastava o executável existir: com o
Docker instalado mas parado, a fixture ``servicos`` quebrava com ``DockerException`` (ERRO em vez
de skip).
"""

import asyncio
import os
import shutil
import sys

import pytest


def docker_disponivel() -> tuple[bool, str]:
    """(pode rodar?, motivo para pular)."""
    if os.environ.get("SORA_TESTE_PG") and os.environ.get("SORA_TESTE_REDIS"):
        return True, ""  # serviços já de pé (contêiner Linux dos testes do navegador)
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


@pytest.fixture(scope="session")
def event_loop_policy():
    """Só os testes de integração usam o loop "selector" no Windows (o checkpointer assíncrono do
    psycopg não roda no Proactor, o padrão). Antes isso era trocado na importação de um módulo e
    valia para a sessão inteira, o que quebrava o Playwright (que precisa do Proactor) nos
    testes de navegador da mesma execução."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()
