"""Confere o contrato OpenAPI, o CORS e a lista de eventos de estado; especificação §§2 e 8.2."""

from fastapi.testclient import TestClient

from app.eventos.tipos import TIPOS_EVENTOS_ESTADO
from app.main import criar_aplicacao


def test_openapi_declara_bearer_e_sse() -> None:
    esquema = criar_aplicacao().openapi()

    assert esquema["components"]["securitySchemes"]["BearerAuth"]["scheme"] == "bearer"
    rota = esquema["paths"]["/v1/eventos"]["get"]
    assert "text/event-stream" in rota["responses"]["200"]["content"]
    assert rota["security"] == [{"BearerAuth": []}]
    assert "security" not in esquema["paths"]["/v1/auth/entrar"]["post"]


def test_cors_libera_tauri_e_bloqueia_outras_origens() -> None:
    with TestClient(criar_aplicacao()) as cliente:
        pedido = {"Access-Control-Request-Method": "GET"}
        ok = cliente.options("/v1/eu", headers={"Origin": "http://tauri.localhost", **pedido})
        ruim = cliente.options("/v1/eu", headers={"Origin": "http://qualquer.com", **pedido})

    assert ok.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert "access-control-allow-origin" not in ruim.headers


def test_lista_central_de_eventos_de_estado() -> None:
    assert len(TIPOS_EVENTOS_ESTADO) == 9
    assert "mensagem.delta" not in TIPOS_EVENTOS_ESTADO
