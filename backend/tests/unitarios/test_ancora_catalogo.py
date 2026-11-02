"""Conectores acima de 20 ferramentas vão pelo catálogo preguiçoso e a execução é revisada
pelo nome da ferramenta de verdade (Âncora, etapa 4)."""

from __future__ import annotations

import json
from uuid import uuid4

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.agentes.ancora import catalogo_dos_conectores
from app.agentes.montagem import ContextoAgente
from app.revisor.execucao import SEM_SUPERVISAO


class Vazio(BaseModel):
    pass


def _ferramenta(nome: str) -> StructuredTool:
    async def rodar() -> str:
        return f"rodou {nome}"

    return StructuredTool.from_function(
        coroutine=rodar, name=nome, description=nome, args_schema=Vazio
    )


def _contexto(sem_supervisao: bool) -> ContextoAgente:
    return ContextoAgente(
        usuario_id=uuid4(),
        agente_id=uuid4(),
        conversa_id=uuid4(),
        papel="individual",
        sem_supervisao=sem_supervisao,
    )


def test_ate_vinte_vao_direto_e_vazio_nao_gera_nada() -> None:
    assert catalogo_dos_conectores([], _contexto(False)) == []
    direto = catalogo_dos_conectores(
        [_ferramenta(f"mcp__x__get_{i}") for i in range(20)], _contexto(False)
    )
    assert len(direto) == 20


async def test_acima_de_vinte_so_tres_meta_ferramentas_e_a_execucao_e_revisada() -> None:
    nomes = [f"mcp__x__get_{i}" for i in range(24)] + ["mcp__x__delete_tudo"]
    catalogo = catalogo_dos_conectores([_ferramenta(n) for n in nomes], _contexto(True))
    assert [t.name for t in catalogo] == [
        "conectores_buscar_ferramentas",
        "conectores_carregar_ferramenta",
        "conectores_executar_ferramenta",
    ]
    buscar, _, executar = catalogo
    achadas = json.loads(await buscar.ainvoke({"consulta": "delete"}))
    identificador = json.dumps(achadas)  # só para achar o id sem depender do formato
    assert "delete_tudo" in identificador
    ids = {item["id"]: item["nome"] if "nome" in item else item["id"] for item in _itens(achadas)}
    id_delete = next(i for i in ids if "delete_tudo" in i or "delete_tudo" in ids[i])
    # rotina sem supervisão: escrita nem roda, e o motivo volta ao modelo como texto
    assert await executar.ainvoke({"id": id_delete, "argumentos": {}}) == f"Erro: {SEM_SUPERVISAO}"
    # leitura segura roda
    id_leitura = next(i for i in _itens_ids(await _todas(buscar)) if "get_3" in i)
    assert await executar.ainvoke({"id": id_leitura, "argumentos": {}}) == "rodou mcp__x__get_3"


def _itens(achadas):
    if isinstance(achadas, dict):
        for valor in achadas.values():
            if isinstance(valor, list):
                yield from (v for v in valor if isinstance(v, dict) and "id" in v)
    elif isinstance(achadas, list):
        yield from (v for v in achadas if isinstance(v, dict) and "id" in v)


def _itens_ids(achadas):
    return [item["id"] for item in _itens(achadas)]


async def _todas(buscar):
    return json.loads(await buscar.ainvoke({"consulta": "get_3"}))
