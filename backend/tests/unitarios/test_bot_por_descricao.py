from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from app import bot_por_descricao as modulo


@pytest.mark.parametrize("resposta", ["invalido", '{"nome":"Sora"}', RuntimeError("429")])
async def test_fallback_sem_perder_navegador(monkeypatch, resposta):
    monkeypatch.setattr(modulo, "contexto_do_usuario", AsyncMock(return_value=None))
    candidato = SimpleNamespace(modelo="teste", provedor=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(modulo, "escolher_modelos", lambda *a: SimpleNamespace(modelos=[candidato]))
    monkeypatch.setattr(modulo, "config_do_provedor", AsyncMock(return_value=None))
    invocar = (
        AsyncMock(side_effect=resposta)
        if isinstance(resposta, Exception)
        else AsyncMock(return_value=AIMessage(content=resposta))
    )
    monkeypatch.setattr(
        modulo, "criar_chat_model", lambda *a, **kw: SimpleNamespace(ainvoke=invocar)
    )
    resultado = await modulo.sugerir_bot(None, uuid4(), "entre no site https://exemplo.com")
    assert "navegador_abrir" in resultado["ferramentas"]
    assert "ler_pagina" in resultado["ferramentas"]
    assert "nome" not in resultado


async def test_sugestao_do_modelo(monkeypatch):
    usuario = uuid4()
    contexto = AsyncMock(return_value=None)
    monkeypatch.setattr(modulo, "contexto_do_usuario", contexto)
    candidato = SimpleNamespace(modelo="teste", provedor=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(modulo, "escolher_modelos", lambda *a: SimpleNamespace(modelos=[candidato]))
    config = AsyncMock(return_value=None)
    monkeypatch.setattr(modulo, "config_do_provedor", config)
    invocar = AsyncMock(
        return_value=AIMessage(
            content='{"nome":"Lume","funcao":"Pesquisa","instrucoes":"Pesquise","ferramentas":["buscar_web"]}'
        )
    )
    monkeypatch.setattr(
        modulo, "criar_chat_model", lambda *a, **kw: SimpleNamespace(ainvoke=invocar)
    )
    resultado = await modulo.sugerir_bot(None, usuario, "pesquise")
    assert resultado["nome"] == "Lume"
    contexto.assert_awaited_once_with(None, usuario)
    config.assert_awaited_once_with(None, usuario, candidato.provedor.id)
