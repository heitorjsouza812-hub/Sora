# ruff: noqa: F811
"""Biblioteca de arquivos com Postgres e Redis reais (API em uvicorn)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.core.config import obter_configuracao
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_api_balcao import PNG
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


async def _enviar(
    cliente: httpx.AsyncClient, auth: dict, nome: str, corpo: bytes, tipo: str
) -> str:
    r = await cliente.post("/v1/anexos", files={"arquivo": (nome, corpo, tipo)}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()["anexo_id"]


async def test_biblioteca_organiza_em_pastas_favoritos_e_filtros(
    mundo: Mundo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PASTA_ARQUIVOS", str(tmp_path))
    obter_configuracao.cache_clear()
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "biblio-a@exemplo.com")
        logo = await _enviar(cliente, auth, "logo.png", PNG, "image/png")
        notas = await _enviar(cliente, auth, "notas_100%.txt", b"ola", "text/plain")
        outra = await _enviar(cliente, auth, "planilha.txt", b"a;b", "text/plain")

        todos = (await cliente.get("/v1/biblioteca/arquivos", headers=auth)).json()
        assert [a["id"] for a in todos["itens"]] == [outra, notas, logo]  # mais novo primeiro
        assert todos["proximo"] is None
        imagens = await cliente.get(
            "/v1/biblioteca/arquivos", headers=auth, params={"tipo": "imagem"}
        )
        assert [a["id"] for a in imagens.json()["itens"]] == [logo]
        busca = await cliente.get("/v1/biblioteca/arquivos", headers=auth, params={"busca": "100%"})
        assert [a["id"] for a in busca.json()["itens"]] == [notas]  # % não vira curinga
        pagina = (
            await cliente.get("/v1/biblioteca/arquivos", headers=auth, params={"limite": 2})
        ).json()
        assert len(pagina["itens"]) == 2 and pagina["proximo"]
        resto = await cliente.get(
            "/v1/biblioteca/arquivos",
            headers=auth,
            params={"limite": 2, "antes": pagina["proximo"]},
        )
        assert [a["id"] for a in resto.json()["itens"]] == [logo]

        # pastas: nome único (sem diferenciar maiúscula), mover, favoritos, sem pasta
        pasta = (
            await cliente.post("/v1/biblioteca/pastas", headers=auth, json={"nome": "Campanha"})
        ).json()
        repetida = await cliente.post(
            "/v1/biblioteca/pastas", headers=auth, json={"nome": "campanha"}
        )
        assert repetida.status_code == 409
        movido = await cliente.patch(
            f"/v1/biblioteca/arquivos/{logo}", headers=auth, json={"pasta_id": pasta["id"]}
        )
        assert movido.json()["pasta_id"] == pasta["id"]
        await cliente.patch(
            f"/v1/biblioteca/arquivos/{notas}", headers=auth, json={"favorito": True}
        )
        da_pasta = await cliente.get(
            "/v1/biblioteca/arquivos", headers=auth, params={"pasta_id": pasta["id"]}
        )
        assert [a["id"] for a in da_pasta.json()["itens"]] == [logo]
        favoritos = await cliente.get(
            "/v1/biblioteca/arquivos", headers=auth, params={"vista": "favoritos"}
        )
        assert [a["id"] for a in favoritos.json()["itens"]] == [notas]
        sem_pasta = await cliente.get(
            "/v1/biblioteca/arquivos", headers=auth, params={"vista": "sem_pasta"}
        )
        assert {a["id"] for a in sem_pasta.json()["itens"]} == {notas, outra}
        pastas = (await cliente.get("/v1/biblioteca/pastas", headers=auth)).json()
        assert [(p["nome"], p["total"]) for p in pastas] == [("Campanha", 1)]
        renomeada = await cliente.patch(
            f"/v1/biblioteca/pastas/{pasta['id']}", headers=auth, json={"nome": "  Lançamento  "}
        )
        assert renomeada.json()["nome"] == "Lançamento"

        # apagar a pasta não apaga o arquivo: ele volta para "Sem pasta"
        apagada = await cliente.delete(f"/v1/biblioteca/pastas/{pasta['id']}", headers=auth)
        assert apagada.status_code == 204
        assert (await cliente.get(f"/v1/anexos/{logo}", headers=auth)).status_code == 200
        sem_pasta = await cliente.get(
            "/v1/biblioteca/arquivos", headers=auth, params={"vista": "sem_pasta"}
        )
        assert logo in {a["id"] for a in sem_pasta.json()["itens"]}

        # outra conta não vê nem mexe
        auth_b = await entrar(cliente, mundo.fabrica, "biblio-b@exemplo.com")
        vazio = (await cliente.get("/v1/biblioteca/arquivos", headers=auth_b)).json()
        assert vazio["itens"] == []
        alheio = await cliente.patch(
            f"/v1/biblioteca/arquivos/{logo}", headers=auth_b, json={"favorito": True}
        )
        assert alheio.status_code == 404
        pasta_b = (
            await cliente.post("/v1/biblioteca/pastas", headers=auth_b, json={"nome": "X"})
        ).json()
        cruzado = await cliente.patch(
            f"/v1/biblioteca/arquivos/{notas}", headers=auth, json={"pasta_id": pasta_b["id"]}
        )
        assert cruzado.status_code == 404
