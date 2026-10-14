"""Teste do endpoint mínimo de saúde; especificação §§2 e 8.3."""

from fastapi.testclient import TestClient

from app.main import criar_aplicacao


def test_health_responde_ok() -> None:
    """Confirma que o processo expõe sua verificação de saúde."""
    with TestClient(criar_aplicacao()) as cliente:
        resposta = cliente.get("/health")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
