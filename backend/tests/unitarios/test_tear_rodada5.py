"""Rodada 5 do Tear: OpenAPI sem rotas duplicadas e log do worker."""

from __future__ import annotations

import io
import logging
import sys
from collections import Counter

from app.main import criar_aplicacao


def test_openapi_tem_uma_operacao_por_metodo_e_caminho(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        esquema = criar_aplicacao().openapi()
    duplicadas = [r.getMessage() for r in caplog.records if "Duplicate" in r.getMessage()]
    assert duplicadas == []
    ids = Counter(
        op["operationId"] for caminho in esquema["paths"].values() for op in caminho.values()
    )
    assert [i for i, n in ids.items() if n > 1] == []
    assert "get" in esquema["paths"]["/v1/navegador/perfis"]
    assert "put" in esquema["paths"]["/v1/agentes/{agente_id}/navegador"]


def test_worker_configura_log_em_utf8(monkeypatch) -> None:
    from workers.__main__ import configurar_log

    saida = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stderr", saida)
    raiz = logging.getLogger()
    antes = (raiz.handlers[:], raiz.level)
    try:
        configurar_log()
        logging.getLogger("arq.worker").info("job → ok ← fim")
        saida.flush()
        texto = saida.buffer.getvalue().decode("utf-8")
        assert "INFO:" in texto and "job → ok ← fim" in texto
    finally:
        raiz.handlers[:], raiz.level = antes
