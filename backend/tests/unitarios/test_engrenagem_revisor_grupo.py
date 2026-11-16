"""Engrenagem: o cartão "Precisa de você" aberto por um bot de grupo leva o grupo.

Sem ``canal_id`` no contexto do revisor o cartão ficava com ``grupo_id`` vazio, e a decisão
(``app/api/aprovacoes.py``) não achava o que retomar: nem conversa (o id é do grupo) nem grupo.
O turno do bot ficava parado para sempre depois de "Permitir".
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.agentes.ancora import catalogo_dos_conectores
from app.agentes.middleware import montar_middleware
from app.agentes.middleware.revisor import MiddlewareRevisor
from app.agentes.montagem import ContextoAgente
from app.llm.falso import criar_modelo_falso


def _contexto_do_grupo() -> ContextoAgente:
    canal = uuid4()
    return ContextoAgente(
        usuario_id=uuid4(),
        agente_id=uuid4(),
        conversa_id=canal,
        papel="canal",
        canal_id=canal,
        tarefa_canal_id=uuid4(),
        revisao_canal=3,
        thread_proprio="canal:tarefa:x:1",
    )


def test_revisor_do_bot_de_grupo_conhece_o_grupo() -> None:
    contexto = _contexto_do_grupo()
    itens = montar_middleware(contexto, [criar_modelo_falso("individual")])
    (revisor,) = [m for m in itens if isinstance(m, MiddlewareRevisor)]
    assert revisor.contexto.canal_id == contexto.canal_id
    assert revisor.contexto.tarefa_canal_id == contexto.tarefa_canal_id
    assert revisor.contexto.revisao_canal == 3


async def test_catalogo_do_bot_de_grupo_confere_com_o_grupo(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from langchain_core.tools import StructuredTool

    vistos: list[Any] = []

    async def conferir_acao(nome, argumentos, contexto, **_):  # type: ignore[no-untyped-def]
        vistos.append((nome, contexto))
        return None

    monkeypatch.setattr("app.revisor.execucao.conferir_acao", conferir_acao)

    async def acao(x: str = "") -> str:
        return "ok"

    conectores = [
        StructuredTool.from_function(coroutine=acao, name=f"mcp__srv__acao_{i}", description="x")
        for i in range(25)
    ]
    contexto = _contexto_do_grupo()
    meta = {f.name: f for f in catalogo_dos_conectores(conectores, contexto)}
    resultado = await meta["conectores_executar_ferramenta"].ainvoke(
        {"id": "mcp__srv__acao_3", "argumentos": {"x": "a"}}
    )
    assert resultado == "ok"
    ((nome, ferramenta_ctx),) = vistos
    assert nome == "mcp__srv__acao_3"  # o revisor decide pelo nome de verdade
    assert ferramenta_ctx.canal_id == contexto.canal_id
    assert ferramenta_ctx.tarefa_canal_id == contexto.tarefa_canal_id
