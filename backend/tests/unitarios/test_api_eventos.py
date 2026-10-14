"""Rotas SSE ``/v1/conversas/{id}/eventos`` e ``/v1/eventos`` (especificação §2)."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import fakeredis
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sse_starlette.sse import EventSourceResponse

from app.api import eventos as rotas
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.eventos.sse import INTERVALO_PING_SEGUNDOS, mensagem_ping
from app.eventos.streams import publicar_evento
from app.eventos.tipos import EtapaAtualizada, SugestoesEvento
from app.main import criar_aplicacao

USUARIO = UUID("12121212-1212-4121-8121-121212121212")
CONVERSA = UUID("11111111-1111-4111-8111-111111111111")


class SessaoFalsa:
    """Responde ao ``select`` da checagem de dono com o resultado combinado."""

    def __init__(self, dona: bool) -> None:
        self.dona = dona
        self.consultas: list[Any] = []

    async def execute(self, consulta: Any) -> "SessaoFalsa":
        self.consultas.append(consulta)
        return self

    def scalar_one_or_none(self) -> UUID | None:
        return CONVERSA if self.dona else None


@pytest.fixture
async def redis() -> AsyncIterator[fakeredis.FakeAsyncRedis]:
    cliente = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield cliente
    await cliente.aclose()


async def test_conversa_do_usuario_filtra_por_usuario() -> None:
    sessao = SessaoFalsa(dona=True)
    assert await rotas.conversa_do_usuario(sessao, CONVERSA, USUARIO)  # type: ignore[arg-type]
    sql = str(sessao.consultas[0])
    assert "conversas.id" in sql and "conversas.usuario_id" in sql
    assert not await rotas.conversa_do_usuario(SessaoFalsa(dona=False), CONVERSA, USUARIO)  # type: ignore[arg-type]


async def test_conversa_de_outro_usuario_da_404(redis: fakeredis.FakeAsyncRedis) -> None:
    with pytest.raises(HTTPException) as erro:
        await rotas.eventos_da_conversa(CONVERSA, USUARIO, SessaoFalsa(dona=False), redis)  # type: ignore[arg-type]
    assert erro.value.status_code == 404


def test_rota_da_conversa_responde_404_por_http() -> None:
    aplicacao = criar_aplicacao()
    aplicacao.dependency_overrides[usuario_atual] = lambda: USUARIO
    aplicacao.dependency_overrides[obter_sessao] = lambda: SessaoFalsa(dona=False)
    aplicacao.dependency_overrides[obter_redis] = lambda: fakeredis.FakeAsyncRedis()
    cliente = TestClient(aplicacao)  # sem ``with``: não roda o lifespan
    resposta = cliente.get(f"/v1/conversas/{uuid4()}/eventos")
    assert resposta.status_code == 404


def test_rotas_exigem_token() -> None:
    cliente = TestClient(criar_aplicacao())  # sem ``with``: não roda o lifespan
    assert cliente.get("/v1/eventos").status_code == 401
    assert cliente.get(f"/v1/conversas/{uuid4()}/eventos").status_code == 401


async def test_rota_da_conversa_retoma_do_last_event_id(
    redis: fakeredis.FakeAsyncRedis,
) -> None:
    ids = [
        await publicar_evento(redis, SugestoesEvento(itens=[str(i)]), CONVERSA, USUARIO)
        for i in range(3)
    ]
    resposta = await rotas.eventos_da_conversa(
        CONVERSA,
        USUARIO,
        SessaoFalsa(dona=True),  # type: ignore[arg-type]
        redis,
        ultimo_evento_id=ids[0],
    )
    assert isinstance(resposta, EventSourceResponse)
    assert resposta.media_type == "text/event-stream"
    assert resposta.ping_interval == INTERVALO_PING_SEGUNDOS
    assert resposta.ping_message_factory is mensagem_ping

    corpo = resposta.body_iterator
    recebidos = [await anext(corpo), await anext(corpo)]  # type: ignore[call-overload]
    await corpo.aclose()  # type: ignore[union-attr]
    assert [m["id"] for m in recebidos] == ids[1:]


async def test_rota_do_usuario_le_o_canal_do_usuario(redis: fakeredis.FakeAsyncRedis) -> None:
    etapa = EtapaAtualizada(
        etapa_id=uuid4(), status="executando", progresso=10, tokens=0, custo_usd=0.0
    )
    await publicar_evento(redis, SugestoesEvento(itens=["fora"]), CONVERSA, USUARIO)
    await publicar_evento(redis, etapa, CONVERSA, USUARIO)

    resposta = await rotas.eventos_do_usuario(USUARIO, redis, ultimo_evento_id="0-0")
    corpo = resposta.body_iterator
    primeira = await anext(corpo)  # type: ignore[call-overload]
    await corpo.aclose()  # type: ignore[union-attr]

    assert primeira["event"] == "etapa.atualizada"
    assert f'"conversa_id":"{CONVERSA}"' in primeira["data"]
