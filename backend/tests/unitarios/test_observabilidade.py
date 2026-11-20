"""Sentry ligado só com ``SENTRY_DSN`` e sem dados pessoais (senhas e chaves passam no corpo)."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.core.observabilidade import iniciar_sentry


def test_sem_dsn_nao_liga() -> None:
    assert iniciar_sentry(SimpleNamespace(sentry_dsn=None, ambiente="teste"), "api") is False  # type: ignore[arg-type]


def test_com_dsn_liga_sem_dados_pessoais(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentry_sdk

    chamadas: list[dict[str, Any]] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **k: chamadas.append(k))
    monkeypatch.setattr(sentry_sdk, "set_tag", lambda *_a: None)
    config = SimpleNamespace(sentry_dsn="https://chave@sentry.exemplo/1", ambiente="producao")
    assert iniciar_sentry(config, "worker") is True  # type: ignore[arg-type]
    (opcoes,) = chamadas
    assert opcoes["send_default_pii"] is False
    assert opcoes["max_request_body_size"] == "never"
    assert opcoes["include_local_variables"] is False
    assert opcoes["environment"] == "producao"
