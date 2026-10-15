"""Redis Streams e SSE dos eventos (especificação §2), com fakeredis.

Inclui os 26 exemplos de ``tests/contrato`` passando pelo publicador e a
reconexão com ``Last-Event-ID`` sem perder nem repetir eventos.
"""

import asyncio
import json
import typing
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import fakeredis
import pytest
from pydantic import BaseModel

from app.eventos.sse import gerar_sse, mensagem_ping, mensagem_sse
from app.eventos.streams import (
    CODIGO_RECARREGAR,
    RETENCAO_SEGUNDOS,
    EventoLido,
    aviso_de_recarga,
    canal_conversa,
    canal_usuario,
    id_minimo_retido,
    id_valido,
    ler_eventos,
    ler_lote,
    perdeu_eventos,
    ponto_de_partida,
    publicar_evento,
)
from app.eventos.tipos import TIPOS_EVENTOS_ESTADO, Evento, SugestoesEvento

CONTRATO = Path(__file__).parents[1] / "contrato"
MODELOS: dict[str, type[BaseModel]] = {m.evento: m for m in typing.get_args(Evento)}
CONVERSA = UUID("11111111-1111-4111-8111-111111111111")  # a mesma dos exemplos
USUARIO = UUID("12121212-1212-4121-8121-121212121212")


@pytest.fixture
async def redis() -> AsyncIterator[fakeredis.FakeAsyncRedis]:
    cliente = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield cliente
    await cliente.aclose()


def _exemplo(caminho: Path) -> dict[str, typing.Any]:
    return json.loads(caminho.read_text(encoding="utf-8"))


def _evento(caminho: Path) -> Evento:
    exemplo = _exemplo(caminho)
    return MODELOS[exemplo["event"]].model_validate(exemplo["data"])  # type: ignore[return-value]


async def _publicar_varios(redis: fakeredis.FakeAsyncRedis, n: int) -> list[str]:
    return [
        await publicar_evento(redis, SugestoesEvento(itens=[f"s{i}"]), CONVERSA, USUARIO)
        for i in range(n)
    ]


# ---------- publicar ----------


@pytest.mark.parametrize("caminho", sorted(CONTRATO.glob("*.json")), ids=lambda c: c.stem)
async def test_contrato_da_conversa_passa_pelo_publicador(
    redis: fakeredis.FakeAsyncRedis, caminho: Path
) -> None:
    exemplo = _exemplo(caminho)
    id_stream = await publicar_evento(redis, _evento(caminho), CONVERSA, USUARIO)

    assert id_valido(id_stream)
    [lido] = await ler_lote(redis, canal_conversa(CONVERSA), "0-0")
    assert lido == EventoLido(id=id_stream, evento=exemplo["event"], dados=exemplo["data"])


@pytest.mark.parametrize(
    "caminho", sorted((CONTRATO / "usuario").glob("*.json")), ids=lambda c: c.stem
)
async def test_contrato_do_usuario_sai_com_conversa_id(
    redis: fakeredis.FakeAsyncRedis, caminho: Path
) -> None:
    exemplo = _exemplo(caminho)
    await publicar_evento(redis, _evento(CONTRATO / caminho.name), CONVERSA, USUARIO)

    [lido] = await ler_lote(redis, canal_usuario(USUARIO), "0-0")
    assert lido.evento == exemplo["event"]
    assert lido.dados == exemplo["data"]


@pytest.mark.parametrize("nome", sorted(set(MODELOS) - set(TIPOS_EVENTOS_ESTADO)), ids=lambda n: n)
async def test_evento_que_nao_e_de_estado_nao_vai_para_o_usuario(
    redis: fakeredis.FakeAsyncRedis, nome: str
) -> None:
    await publicar_evento(redis, _evento(CONTRATO / f"{nome}.json"), CONVERSA, USUARIO)
    assert await redis.exists(canal_usuario(USUARIO)) == 0


async def test_stream_expira_em_24_horas(redis: fakeredis.FakeAsyncRedis) -> None:
    await publicar_evento(redis, _evento(CONTRATO / "etapa.atualizada.json"), CONVERSA, USUARIO)
    for canal in (canal_conversa(CONVERSA), canal_usuario(USUARIO)):
        ttl = await redis.ttl(canal)
        assert RETENCAO_SEGUNDOS - 5 <= ttl <= RETENCAO_SEGUNDOS


async def test_publicar_corta_eventos_com_mais_de_24_horas(
    redis: fakeredis.FakeAsyncRedis,
) -> None:
    canal = canal_conversa(CONVERSA)
    await redis.xadd(canal, {"event": "ping", "data": "{}"}, id="1000-0")
    novo = (await _publicar_varios(redis, 1))[0]

    ids = [e.id for e in await ler_lote(redis, canal, "0-0")]
    assert ids == [novo]


def test_id_minimo_retido() -> None:
    agora = 1_800_000_000_000
    assert id_minimo_retido(agora) == f"{agora - RETENCAO_SEGUNDOS * 1000}-0"
    assert id_minimo_retido(10) == "0-0"


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("1697040000000-0", True),
        ("0-0", True),
        ("42", False),
        ("", False),
        ("abc-1", False),
        ("1-2-3", False),
        (None, False),
    ],
)
def test_id_valido(valor: str | None, esperado: bool) -> None:
    assert id_valido(valor) is esperado


# ---------- ler e reconectar ----------


async def test_reconectar_com_last_event_id_nao_perde_nem_repete(
    redis: fakeredis.FakeAsyncRedis,
) -> None:
    canal = canal_conversa(CONVERSA)
    ids = await _publicar_varios(redis, 3)

    # 1ª conexão: o app recebe os 3 e cai.
    primeira = await ler_lote(redis, canal, "0-0")
    assert [e.id for e in primeira] == ids
    ultimo_recebido = primeira[1].id  # caiu depois do 2º

    # enquanto estava fora, chegam mais 2
    ids += await _publicar_varios(redis, 2)

    # reconecta com Last-Event-ID = o último que ele viu
    inicio = await ponto_de_partida(redis, canal, ultimo_recebido)
    segunda = await ler_lote(redis, canal, inicio)
    assert [e.id for e in segunda] == ids[2:]
    vistos = [e.id for e in primeira[:2]] + [e.id for e in segunda]
    assert vistos == ids
    assert len(set(vistos)) == len(vistos)


async def test_sem_last_event_id_comeca_no_fim(redis: fakeredis.FakeAsyncRedis) -> None:
    canal = canal_conversa(CONVERSA)
    antigos = await _publicar_varios(redis, 2)
    inicio = await ponto_de_partida(redis, canal, None)
    assert inicio == antigos[-1]
    novos = await _publicar_varios(redis, 1)
    assert [e.id for e in await ler_lote(redis, canal, inicio)] == novos


async def test_last_event_id_invalido_vale_como_ausente(
    redis: fakeredis.FakeAsyncRedis,
) -> None:
    canal = canal_conversa(CONVERSA)
    ids = await _publicar_varios(redis, 2)
    assert await ponto_de_partida(redis, canal, "lixo") == ids[-1]


async def test_stream_vazio_comeca_do_zero(redis: fakeredis.FakeAsyncRedis) -> None:
    assert await ponto_de_partida(redis, canal_conversa(uuid4()), None) == "0-0"


async def test_ler_eventos_entrega_none_quando_nada_chega(
    redis: fakeredis.FakeAsyncRedis,
) -> None:
    leitor = ler_eventos(redis, canal_conversa(CONVERSA), None, bloquear_ms=10)
    assert await anext(leitor) is None
    await leitor.aclose()


async def test_ler_eventos_acorda_com_evento_novo(redis: fakeredis.FakeAsyncRedis) -> None:
    canal = canal_conversa(CONVERSA)
    leitor = ler_eventos(redis, canal, None, bloquear_ms=2_000)

    async def publicar_depois() -> str:
        await asyncio.sleep(0.05)
        return (await _publicar_varios(redis, 1))[0]

    tarefa = asyncio.create_task(publicar_depois())
    lido = await asyncio.wait_for(anext(leitor), timeout=3)
    assert lido is not None and lido.id == await tarefa
    await leitor.aclose()


# ---------- Last-Event-ID mais velho que a retenção (rodada 3, item 17) ----------


async def _stream_cortado(redis: fakeredis.FakeAsyncRedis) -> tuple[str, list[str]]:
    """Um evento de mais de 24 h (que o app recebeu) e outro logo depois, que ele não viu:
    os dois são cortados pelo ``MINID`` quando chega um evento novo."""
    canal = canal_conversa(CONVERSA)
    await redis.xadd(canal, {"event": "sugestoes", "data": "{}"}, id="1000-0")
    await redis.xadd(canal, {"event": "sugestoes", "data": "{}"}, id="2000-0")  # perdido
    novos = await _publicar_varios(redis, 2)
    return "1000-0", novos


async def test_last_event_id_cortado_avisa_para_recarregar(
    redis: fakeredis.FakeAsyncRedis,
) -> None:
    canal = canal_conversa(CONVERSA)
    visto, novos = await _stream_cortado(redis)
    assert await perdeu_eventos(redis, canal, visto)

    leitor = ler_eventos(redis, canal, visto, bloquear_ms=2_000)
    aviso = await anext(leitor)
    assert aviso is not None
    assert aviso.evento == "erro" and aviso.dados["codigo"] == CODIGO_RECARREGAR
    assert aviso.id == novos[-1]  # reconectar com esse id não repete o aviso
    assert not await perdeu_eventos(redis, canal, aviso.id)

    # segue do fim do stream, como uma conexão nova (o app recarregou o estado pela API)
    depois = (await _publicar_varios(redis, 1))[0]
    lido = await asyncio.wait_for(anext(leitor), timeout=3)
    assert lido is not None and lido.id == depois
    await leitor.aclose()


async def test_last_event_id_cortado_no_sse(redis: fakeredis.FakeAsyncRedis) -> None:
    visto, novos = await _stream_cortado(redis)
    gerador = gerar_sse(redis, canal_conversa(CONVERSA), visto, bloquear_ms=10)
    mensagem = await anext(gerador)
    await gerador.aclose()
    assert mensagem["event"] == "erro" and mensagem["id"] == novos[-1]
    assert json.loads(mensagem["data"])["codigo"] == CODIGO_RECARREGAR


async def test_stream_expirado_com_id_antigo_avisa(redis: fakeredis.FakeAsyncRedis) -> None:
    canal = canal_conversa(uuid4())  # a chave sumiu (EXPIRE de 24 h)
    assert await perdeu_eventos(redis, canal, "1000-0")
    leitor = ler_eventos(redis, canal, "1000-0", bloquear_ms=10)
    aviso = await anext(leitor)
    assert aviso is not None and aviso.dados["codigo"] == CODIGO_RECARREGAR
    assert aviso.id == "0-0"
    await leitor.aclose()


async def test_id_retido_ou_sem_id_nao_avisa(redis: fakeredis.FakeAsyncRedis) -> None:
    canal = canal_conversa(CONVERSA)
    ids = await _publicar_varios(redis, 3)
    for valor in (ids[0], ids[1], ids[-1], None, "lixo", "0-0"):
        assert not await perdeu_eventos(redis, canal, valor)
    # stream vazio e id recente: a chave não expirou, nada se perdeu
    assert not await perdeu_eventos(redis, canal_conversa(uuid4()), ids[-1])


async def test_id_antigo_ainda_guardado_nao_avisa(redis: fakeredis.FakeAsyncRedis) -> None:
    """Sem ``XADD`` novo, nada foi cortado: o id de mais de 24 h ainda está no stream."""
    canal = canal_conversa(CONVERSA)
    await redis.xadd(canal, {"event": "sugestoes", "data": "{}"}, id="1000-0")
    await redis.xadd(canal, {"event": "sugestoes", "data": "{}"}, id="2000-0")
    assert not await perdeu_eventos(redis, canal, "1000-0")
    assert [e.id for e in await ler_lote(redis, canal, "1000-0")] == ["2000-0"]


def test_aviso_de_recarga_bate_com_o_contrato() -> None:
    exemplo = _exemplo(CONTRATO / "retomada" / "erro.json")
    aviso = aviso_de_recarga(exemplo["id"])
    assert {"id": aviso.id, "event": aviso.evento, "data": aviso.dados} == exemplo


# ---------- SSE ----------


async def test_gerar_sse_retoma_e_formata(redis: fakeredis.FakeAsyncRedis) -> None:
    canal = canal_conversa(CONVERSA)
    ids = await _publicar_varios(redis, 3)

    gerador = gerar_sse(redis, canal, ids[0], bloquear_ms=10)
    mensagens = [await anext(gerador), await anext(gerador)]
    await gerador.aclose()

    assert [m["id"] for m in mensagens] == ids[1:]
    assert mensagens[0]["event"] == "sugestoes"
    assert json.loads(mensagens[0]["data"]) == {"itens": ["s1"]}


def test_mensagem_sse_usa_json_compacto() -> None:
    m = mensagem_sse(EventoLido(id="1-0", evento="erro", dados={"codigo": "x", "mensagem": "ã"}))
    assert m == {"id": "1-0", "event": "erro", "data": '{"codigo":"x","mensagem":"ã"}'}


def test_ping_sem_id_e_sem_dados() -> None:
    ping = mensagem_ping()
    assert ping.event == "ping"
    assert ping.data == "{}"
    assert ping.id is None
