"""``executar_comando`` com Docker de verdade: contêiner descartável, sem rede, sem root, com
prazo; e a trava de produção (só com host separado)."""

from __future__ import annotations

import subprocess
from uuid import uuid4

import pytest

from app.computador import ExecutarComando
from app.computador.ferramenta import executar_comando
from app.core.config import obter_configuracao
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta

pytestmark = pytest.mark.integracao


def _ctx(**extra) -> ContextoFerramenta:
    return ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4(), **extra)


@pytest.fixture
def docker_ligado(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AMBIENTE", "desenvolvimento")
    monkeypatch.setenv("SANDBOX_PROVEDOR", "docker")
    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()


async def test_comando_roda_isolado(docker_ligado) -> None:
    saida = await executar_comando(
        ExecutarComando(comando="echo oi; id -u; touch /etc/x || echo somente-leitura"), _ctx()
    )
    assert "código de saída: 0" in saida and "oi" in saida
    assert "65534" in saida and "somente-leitura" in saida


async def test_sem_rede_por_padrao(docker_ligado) -> None:
    cmd = "python -c \"import socket; socket.create_connection(('1.1.1.1', 53), 3)\""
    saida = await executar_comando(ExecutarComando(comando=cmd), _ctx())
    assert "código de saída: 1" in saida


async def test_prazo_estourado_remove_o_conteiner(docker_ligado) -> None:
    saida = await executar_comando(ExecutarComando(comando="sleep 60", prazo_segundos=1), _ctx())
    assert "prazo estourado" in saida
    vivos = subprocess.run(  # noqa: ASYNC221
        ["docker", "ps", "-q", "--filter", "label=sora.sandbox=1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert vivos == ""


async def test_rotina_sem_supervisao_nao_usa(docker_ligado) -> None:
    with pytest.raises(ErroFerramenta, match="sem supervisão"):
        await executar_comando(ExecutarComando(comando="echo x"), _ctx(sem_supervisao=True))


def test_producao_exige_host_separado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("SANDBOX_PROVEDOR", "docker")
    monkeypatch.delenv("SANDBOX_DOCKER_HOST", raising=False)
    obter_configuracao.cache_clear()
    assert obter_configuracao().sandbox_ativo is False
    monkeypatch.setenv("SANDBOX_DOCKER_HOST", "ssh://sandbox@host-separado")
    obter_configuracao.cache_clear()
    assert obter_configuracao().sandbox_ativo is True
    monkeypatch.setenv("SANDBOX_PROVEDOR", "nenhum")
    obter_configuracao.cache_clear()
    assert obter_configuracao().sandbox_ativo is False
    obter_configuracao.cache_clear()


async def test_producao_sem_host_recusa_a_ferramenta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("SANDBOX_PROVEDOR", "docker")
    monkeypatch.delenv("SANDBOX_DOCKER_HOST", raising=False)
    obter_configuracao.cache_clear()
    with pytest.raises(ErroFerramenta, match="desligado"):
        await executar_comando(ExecutarComando(comando="echo x"), _ctx())
    obter_configuracao.cache_clear()
