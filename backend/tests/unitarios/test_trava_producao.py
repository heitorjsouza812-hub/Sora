"""O startup recusa o modelo falso em produção; especificação §8.3."""

import pytest
from fastapi import FastAPI

from app.core.config import obter_configuracao
from app.llm.falso import ModeloFalsoEmProducao
from app.main import ciclo_de_vida


@pytest.fixture(autouse=True)
def _limpar_cache():
    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()


async def test_producao_com_modelo_falso_nao_sobe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    with pytest.raises(ModeloFalsoEmProducao):
        async with ciclo_de_vida(FastAPI()):
            pass


async def test_desenvolvimento_com_modelo_falso_sobe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "desenvolvimento")
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    app = FastAPI()
    async with ciclo_de_vida(app):
        assert app.state.redis is not None


async def test_producao_com_busca_falsa_nao_sobe(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.busca.provedor import BuscaProibidaEmProducao

    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("BUSCA_PROVEDOR", "falso")
    with pytest.raises(BuscaProibidaEmProducao):
        async with ciclo_de_vida(FastAPI()):
            pass
