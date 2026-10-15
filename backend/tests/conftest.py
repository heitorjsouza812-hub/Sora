"""Fixtures compartilhados pelos testes do backend; especificação §8.5."""

import base64
import os
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

# Valores fictícios só para o processo de teste carregar a configuração. Sem ``AMBIENTE`` a
# configuração vale ``producao`` (segura por padrão), então os testes declaram ``teste``. O
# ``JWT_SEGREDO`` tem 32+ bytes para os testes que trocam o ambiente para produção.
os.environ.setdefault("AMBIENTE", "teste")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://teste:teste@localhost/teste")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault(
    "CHAVE_MESTRA", base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
)
os.environ.setdefault("JWT_SEGREDO", "jwt-local-dos-testes-0123456789abcdef0123")

from app.main import criar_aplicacao


@pytest.fixture
def aplicacao() -> FastAPI:
    """Cria uma aplicação isolada para cada teste."""
    return criar_aplicacao()


@pytest.fixture
async def cliente(aplicacao: FastAPI) -> AsyncIterator[AsyncClient]:
    """Fornece um cliente HTTP assíncrono quando o transporte for implementado."""
    raise NotImplementedError
    yield  # pragma: no cover
