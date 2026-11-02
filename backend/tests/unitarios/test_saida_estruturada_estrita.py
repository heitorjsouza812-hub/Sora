"""Saída estruturada no modo estrito (Groq/OpenAI): teste real com a Groq, 2026-11-02.

A Groq recusou o ``DecisaoLider`` ("required is required to be supplied and to be an array
including every key in properties") e o canal de equipe parou. Aqui cada esquema mandado como
``response_format`` passa pelas regras do modo estrito, do jeito que o ``ChatLiteLLM`` monta.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from app.canais_equipe.roteamento import DecisaoLider, conferir_decisao
from app.llm.estruturada import (
    com_saida_estruturada,
    esquema_enviado,
    instrucoes_json,
    violacoes_modo_estrito,
)

# todo esquema usado com saída estruturada (response_format) entra aqui
ESQUEMAS_ESTRUTURADOS: dict[str, type[BaseModel]] = {"DecisaoLider": DecisaoLider}

RAIZ = Path(__file__).resolve().parents[2]


def _esquema_do_chatlitellm(esquema: type[BaseModel]) -> dict[str, Any]:
    pytest.importorskip("langchain_litellm")
    from langchain_litellm import ChatLiteLLM

    cadeia = ChatLiteLLM(model="groq/llama-3.3-70b-versatile", api_key="x")
    formato = cadeia.with_structured_output(esquema).first.kwargs["response_format"]
    assert formato["json_schema"]["strict"] is True
    return formato["json_schema"]["schema"]


@pytest.mark.parametrize("nome", sorted(ESQUEMAS_ESTRUTURADOS))
def test_esquema_enviado_respeita_o_modo_estrito(nome: str) -> None:
    esquema = ESQUEMAS_ESTRUTURADOS[nome]
    assert violacoes_modo_estrito(_esquema_do_chatlitellm(esquema)) == []
    assert violacoes_modo_estrito(esquema_enviado(esquema)) == []


def test_conferidor_pega_o_que_a_groq_recusa() -> None:
    class Ruim(BaseModel):
        a: str
        b: str | None = None
        c: str = ""

    erros = violacoes_modo_estrito(esquema_enviado(Ruim))
    assert any("required" in e for e in erros)
    assert any("'default'" in e for e in erros)
    aninhado = {
        "type": "object",
        "properties": {"x": {"type": "object", "properties": {"y": {"type": "string"}}}},
        "required": ["x"],
        "additionalProperties": False,
    }
    assert any("/properties/x" in e for e in violacoes_modo_estrito(aninhado))


def test_todo_uso_de_saida_estruturada_esta_auditado() -> None:
    """Quem passar a usar response_format precisa entrar em ESQUEMAS_ESTRUTURADOS."""
    chamada = re.compile(r"(?:with_structured_output|com_saida_estruturada)\(\s*[^,]+,\s*(\w+)")
    achados: set[str] = set()
    for pasta in ("app", "workers"):
        for arquivo in (RAIZ / pasta).rglob("*.py"):
            if arquivo.name in {"falso.py", "estruturada.py"}:
                continue
            texto = arquivo.read_text(encoding="utf-8")
            achados.update(chamada.findall(texto))
            for m in re.finditer(r"\.with_structured_output\(\s*(\w+)", texto):
                achados.add(m.group(1))
            assert '"json_schema"' not in texto, f"response_format solto em {arquivo}"
    assert achados, "nenhum uso encontrado: a busca quebrou"
    assert achados <= set(ESQUEMAS_ESTRUTURADOS), achados - set(ESQUEMAS_ESTRUTURADOS)


def test_decisao_estrita_com_nulos_e_parcial_do_modelo_falso_sao_aceitas() -> None:
    from app.canais_equipe.roteamento import Membro

    membro = Membro(id=uuid4(), nome="Nina", funcao="textos", disponivel=True)
    estrita = {"acao": "atribuir", "agentes": [str(membro.id)], "tarefa_id": None,
               "pergunta": None}  # fmt: skip
    for bruto in (estrita, {"acao": "atribuir", "agentes": [str(membro.id)]}, {**estrita, "x": 1}):
        conferida = conferir_decisao(bruto, membros=[membro], tarefas=[], texto="post")
        assert conferida.rota is not None and conferida.rota.agentes == (membro.id,), bruto
    for ruim in (
        {**estrita, "agentes": ["não é id"]},
        {**estrita, "acao": "perguntar", "pergunta": "x" * 501},
        {**estrita, "agentes": [str(uuid4()) for _ in range(50)]},
        "[]",
    ):
        assert conferir_decisao(ruim, membros=[membro], tarefas=[], texto="post").ilegivel


class _ModeloDeTeste:
    """Provedor que recusa json_schema estrito (400) e aceita json_object."""

    def __init__(self) -> None:
        self.metodos: list[str] = []

    def with_structured_output(self, esquema: Any, *, method: str, **_: Any) -> Any:
        import litellm

        def responder(_entrada: Any) -> Any:
            self.metodos.append(method)
            if method == "json_schema":
                raise litellm.BadRequestError(
                    "invalid JSON schema for response_format", model="m", llm_provider="groq"
                )
            return esquema(acao="sem_resposta", agentes=None, tarefa_id=None, pergunta=None)

        return RunnableLambda(responder)


async def test_provedor_sem_modo_estrito_cai_para_json_object() -> None:
    modelo = _ModeloDeTeste()
    decisao = await com_saida_estruturada(modelo, DecisaoLider).ainvoke("oi")
    assert isinstance(decisao, DecisaoLider) and decisao.acao == "sem_resposta"
    assert modelo.metodos == ["json_schema", "json_mode"]
    assert '"required"' in instrucoes_json(DecisaoLider)
