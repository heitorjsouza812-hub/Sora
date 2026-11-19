"""Turno de item da fila cancelado (prazo do job do ARQ, worker desligando): o item falha e a
fila do bot recebe um novo despacho. Antes o despacho só acontecia em erro comum e os próximos
itens ficavam parados até alguém mandar outra mensagem para o bot."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from workers import equipe


async def test_item_cancelado_falha_e_despacha_o_proximo(monkeypatch: pytest.MonkeyPatch) -> None:
    item = SimpleNamespace(id=uuid4(), agente_id=uuid4())
    falhas: list[str] = []
    despachos: list[dict[str, object]] = []

    class _Fila:
        def __init__(self, _armazem: object) -> None:
            pass

        async def iniciar(self, *_: object) -> SimpleNamespace:
            return item

        async def rodando(self, *_: object) -> None:
            return None

        async def falhar(self, _id: object, _agente: object, motivo: str) -> None:
            falhas.append(motivo)

    class _Sessao:
        async def commit(self) -> None:
            return None

    @asynccontextmanager
    async def sessoes():
        yield _Sessao()

    @asynccontextmanager
    async def batimento(*_: object):
        yield

    async def rodar_turno_do_item(*_: object) -> None:
        raise asyncio.CancelledError

    async def enfileirar(job: str, **args: object) -> None:
        despachos.append({"job": job, **args})

    monkeypatch.setattr(equipe, "FilaAgente", _Fila)
    monkeypatch.setattr(equipe, "ArmazemFilaSQL", lambda sessao: sessao)
    monkeypatch.setattr(equipe, "batimento", batimento)
    monkeypatch.setattr(equipe, "enfileirar", enfileirar)
    monkeypatch.setattr("workers.conversa.rodar_turno_do_item", rodar_turno_do_item)

    agente = str(item.agente_id)
    with pytest.raises(asyncio.CancelledError):
        await equipe.executar_item_fila(
            {"sessoes": sessoes, "redis_eventos": None}, str(item.id), agente
        )
    assert falhas == ["CancelledError"]
    assert despachos == [{"job": "despachar_equipe", "agente_id": agente}]
