# ruff: noqa: F811
"""A API de conectores divulga ferramentas reais, sem montar um catálogo de execução."""

import pytest
from langchain_core.tools import StructuredTool

from tests.integracao.test_fase_b_pronto import (  # noqa: F401
    ambiente_fase_b,
    entrar,
    servicos_fase_b,
)

pytestmark = pytest.mark.integracao


@pytest.mark.parametrize("quantidade", [5, 25])
async def test_conexao_mcp_lista_os_nomes_reais(
    ambiente_fase_b, monkeypatch: pytest.MonkeyPatch, quantidade: int
) -> None:
    class ClienteMCP:
        def __init__(self, conexoes):
            assert list(conexoes) == ["inventario"]

        async def get_tools(self, *, server_name):
            assert server_name == "inventario"

            async def consultar() -> str:
                pytest.fail("O teste de conexão nunca executa ferramentas")

            return [
                StructuredTool.from_function(
                    coroutine=consultar, name=f"get_item_{i}", description="Consulta um item"
                )
                for i in range(quantidade)
            ]

    monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", ClienteMCP)
    cliente, fabrica, _ = ambiente_fase_b
    auth = await entrar(cliente, fabrica, f"mcp-catalogo-{quantidade}@exemplo.com")
    resposta = await cliente.post(
        "/v1/conectores",
        headers=auth,
        json={"nome": "Inventario", "url": "http://127.0.0.1:8080/mcp"},
    )
    assert resposta.status_code == 201, resposta.text
    conector_id = resposta.json()["id"]

    teste = await cliente.post(f"/v1/conectores/{conector_id}/testar", headers=auth)
    assert teste.status_code == 200, teste.text
    assert teste.json() == {
        "ok": True,
        "erro": None,
        "ferramentas": [f"mcp__inventario__get_item_{i}" for i in range(quantidade)],
    }
    lista = await cliente.get("/v1/conectores", headers=auth)
    assert lista.status_code == 200, lista.text
    (conector,) = lista.json()
    assert conector["estado"] == "ok" and conector["n_ferramentas"] == quantidade
