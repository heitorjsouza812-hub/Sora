"""``/health/pronto``: 200 só com banco e Redis respondendo; ``/health`` não toca em nenhum."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core import saude
from app.main import criar_aplicacao


@pytest.mark.parametrize(
    ("banco", "redis", "codigo"),
    [(True, True, 200), (False, True, 503), (True, False, 503)],
)
def test_pronto_reflete_banco_e_redis(
    monkeypatch: pytest.MonkeyPatch, banco: bool, redis: bool, codigo: int
) -> None:
    async def banco_ok() -> bool:
        if not banco:
            raise ConnectionError("banco fora")
        return True

    async def redis_ok(_app: Any) -> bool:
        return redis

    monkeypatch.setattr(saude, "_banco_ok", banco_ok)
    monkeypatch.setattr(saude, "_redis_ok", redis_ok)
    app = criar_aplicacao()
    with TestClient(app) as c:
        r = c.get("/health/pronto")
        assert c.get("/health").status_code == 200
    assert r.status_code == codigo
    assert r.json()["banco"] == ("ok" if banco else "falhou")
