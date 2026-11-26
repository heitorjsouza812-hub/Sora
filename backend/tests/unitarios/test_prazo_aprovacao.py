"""A validade de produção não aceita o prazo reduzido da suíte."""

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
