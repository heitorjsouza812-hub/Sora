"""Engrenagem: o catálogo preguiçoso não é atalho para pular o revisor.

A execução pela meta-ferramenta passa por ``conferir_acao`` com o nome de verdade; negada, a
ferramenta não roda e o modelo recebe o motivo; o cartão (``interrupt``) atravessa o catálogo.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain_core.tools import StructuredTool
from langgraph.errors import GraphInterrupt

from app.agentes.ancora import catalogo_dos_conectores
from app.agentes.montagem import ContextoAgente
from app.revisor.politica import politica_da_ferramenta


def _catalogo(executadas: list[str]) -> dict[str, Any]:
    async def acao(x: str = "") -> str:
        executadas.append(x)
        return "ok"

    conectores = [
        StructuredTool.from_function(coroutine=acao, name=f"mcp__srv__apagar_{i}", description="x")
        for i in range(25)
    ]
    contexto = ContextoAgente(
        usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4(), papel="individual"
    )
    return {f.name: f for f in catalogo_dos_conectores(conectores, contexto)}


async def test_acao_negada_pelo_revisor_nao_roda(monkeypatch: pytest.MonkeyPatch) -> None:
    async def negar(nome, argumentos, contexto, **_):  # type: ignore[no-untyped-def]
        return "O usuário recusou esta ação."

    monkeypatch.setattr("app.revisor.execucao.conferir_acao", negar)
    executadas: list[str] = []
    meta = _catalogo(executadas)
    resultado = await meta["conectores_executar_ferramenta"].ainvoke(
        {"id": "mcp__srv__apagar_1", "argumentos": {"x": "tudo"}}
    )
    assert executadas == []
    assert "recusou" in resultado


async def test_cartao_atravessa_o_catalogo(monkeypatch: pytest.MonkeyPatch) -> None:
    async def pedir_cartao(nome, argumentos, contexto, **_):  # type: ignore[no-untyped-def]
        raise GraphInterrupt(())

    monkeypatch.setattr("app.revisor.execucao.conferir_acao", pedir_cartao)
    executadas: list[str] = []
    meta = _catalogo(executadas)
    with pytest.raises(GraphInterrupt):
        await meta["conectores_executar_ferramenta"].ainvoke(
            {"id": "mcp__srv__apagar_1", "argumentos": {"x": "tudo"}}
        )
    assert executadas == []


async def test_id_desconhecido_e_argumento_invalido_voltam_como_erro() -> None:
    meta = _catalogo([])
    executar = meta["conectores_executar_ferramenta"]
    assert (await executar.ainvoke({"id": "nao_existe", "argumentos": {}})).startswith("Erro:")
    errado = await executar.ainvoke({"id": "mcp__srv__apagar_1", "argumentos": {"x": 3}})
    assert errado.startswith("Erro:")


def test_meta_ferramentas_de_busca_sao_livres_e_a_execucao_e_revisada_por_dentro() -> None:
    from app.revisor.execucao import cuida_do_proprio_cartao

    assert politica_da_ferramenta("conectores_buscar_ferramentas").value == "livre"
    assert cuida_do_proprio_cartao("conectores_executar_ferramenta")
    assert cuida_do_proprio_cartao("navegador_executar_ferramenta")
