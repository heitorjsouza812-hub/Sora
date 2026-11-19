"""Corpo acima de 25 MB vira 413 antes de a rota ler o multipart (o /tmp do contêiner é 64 MB)."""

from fastapi import FastAPI, Request, UploadFile
from fastapi.testclient import TestClient

from app.core.corpo import LimiteDeCorpo


def _app(maximo: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(LimiteDeCorpo, maximo=maximo)

    @app.post("/eco")
    async def eco(requisicao: Request) -> dict[str, int]:
        return {"tamanho": len(await requisicao.body())}

    @app.post("/arquivo")
    async def arquivo(arquivo: UploadFile) -> dict[str, int]:
        return {"tamanho": len(await arquivo.read())}

    return app


def test_corpo_dentro_do_limite_passa() -> None:
    with TestClient(_app(1000)) as c:
        assert c.post("/eco", content=b"x" * 500).json() == {"tamanho": 500}


def test_content_length_acima_do_limite_e_413_sem_ler() -> None:
    with TestClient(_app(1000)) as c:
        r = c.post("/eco", content=b"x" * 5000)
    assert r.status_code == 413 and "25 MB" in r.json()["detail"]


def test_corpo_sem_content_length_e_contado_no_fluxo() -> None:
    def pedacos():
        for _ in range(10):
            yield b"x" * 500

    with TestClient(_app(1000)) as c:
        r = c.post("/eco", content=pedacos())
    assert r.status_code == 413


def test_multipart_grande_e_413() -> None:
    with TestClient(_app(10_000)) as c:
        r = c.post("/arquivo", files={"arquivo": ("a.txt", b"x" * 50_000, "text/plain")})
    assert r.status_code == 413
