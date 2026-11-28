"""Decisões de aprovação pelo HTTP e efeitos observados no Postgres."""

import asyncio
from uuid import uuid4

import httpx
import pytest

from tests.ponta_a_ponta.http import criar_conversa, entrar, estado_final_da_fila, ler_ate, sql

pytestmark = [pytest.mark.integracao, pytest.mark.asyncio]


@pytest.fixture
async def tabela_de_efeitos(mundo):
    await sql(mundo, "create table if not exists efeitos_e2e (conversa_id uuid not null)")


async def _contar_efeitos(mundo, conversa):
    linhas = await sql(
        mundo, "select count(*) as total from efeitos_e2e where conversa_id = :id", id=conversa
    )
    return linhas[0].total


async def _pedido(cliente, mundo):
    conversa = await criar_conversa(cliente, "Registre a ação [efeito_teste]")
    eventos = await ler_ate(cliente, conversa, lambda evento: evento.nome == "aprovacao.pedida")
    assert await _contar_efeitos(mundo, conversa) == 0
    return conversa, eventos[-1]


async def _decidir(cliente, cartao, decisao="permitir_uma_vez"):
    return await cliente.post(
        f"/v1/aprovacoes/{cartao.dados['aprovacao_id']}/decidir",
        json={"decisao": decisao},
    )


async def _conferir_fim(cliente, mundo, conversa, cartao, status, efeitos):
    eventos = await ler_ate(
        cliente, conversa, lambda evento: evento.nome == "mensagem.fim", cursor=cartao.id
    )
    assert [
        evento.dados["status"] for evento in eventos if evento.nome == "aprovacao.resolvida"
    ] == [status]
    assert await _contar_efeitos(mundo, conversa) == efeitos
    resposta = "".join(
        evento.dados["texto"] for evento in eventos if evento.nome == "mensagem.delta"
    )
    esperado = "A ação foi realizada." if efeitos else "A ação não foi realizada."
    assert esperado in resposta


@pytest.mark.usefixtures("tabela_de_efeitos")
@pytest.mark.parametrize(
    ("decisao", "status", "efeitos"),
    [("permitir_uma_vez", "permitida", 1), ("negar", "negada", 0)],
    ids=["permitir", "recusar"],
)
async def test_decisao_retoma_o_turno(cliente_e2e, mundo, decisao, status, efeitos):
    await mundo.iniciar_worker()
    conversa, cartao = await _pedido(cliente_e2e, mundo)
    resposta = await _decidir(cliente_e2e, cartao, decisao)
    assert resposta.status_code == 204, resposta.text
    await _conferir_fim(cliente_e2e, mundo, conversa, cartao, status, efeitos)


@pytest.mark.usefixtures("tabela_de_efeitos")
async def test_cartao_de_outra_conta_nao_retoma_pedido(cliente_e2e, mundo):
    await mundo.iniciar_worker()
    conversa, cartao = await _pedido(cliente_e2e, mundo)
    async with httpx.AsyncClient(base_url=mundo.url, timeout=15) as outro_cliente:
        outro_cliente.headers.update(
            await entrar(outro_cliente, mundo, f"{uuid4().hex}@exemplo.com")
        )
        outra_conversa, outro_cartao = await _pedido(outro_cliente, mundo)
        resposta = await _decidir(outro_cliente, cartao)
        assert resposta.status_code in {403, 404}, resposta.text

    for id_conversa, evento in [(conversa, cartao), (outra_conversa, outro_cartao)]:
        aprovacoes = await sql(
            mundo, "select status from aprovacoes where id = :id", id=evento.dados["aprovacao_id"]
        )
        assert aprovacoes[0].status == "pendente"
        assert await _contar_efeitos(mundo, id_conversa) == 0


@pytest.mark.usefixtures("tabela_de_efeitos")
async def test_permitir_cartao_do_pedido_parado_nao_retoma(cliente_e2e, mundo, aguardar_job):
    await mundo.iniciar_worker()
    conversa, cartao = await _pedido(cliente_e2e, mundo)
    # A fila fecha o item inicial só depois de gravar o checkpoint da pausa.
    assert await estado_final_da_fila(mundo, conversa) == "concluido"
    parada = await cliente_e2e.post(f"/v1/conversas/{conversa}/parar")
    assert parada.status_code == 202, parada.text

    resposta = await _decidir(cliente_e2e, cartao)
    assert resposta.status_code == 204, resposta.text
    aprovacao_id = cartao.dados["aprovacao_id"]
    await aguardar_job(f"aprovacao:{aprovacao_id}")
    eventos = await ler_ate(
        cliente_e2e, conversa, lambda evento: evento.nome == "aprovacao.resolvida", cursor=cartao.id
    )
    assert eventos[-1].dados["aprovacao_id"] == aprovacao_id
    assert eventos[-1].dados["status"] == "permitida"
    assert await _contar_efeitos(mundo, conversa) == 0
    mensagens = await sql(
        mundo,
        "select autor, estado from mensagens where conversa_id = :id and visivel",
        id=conversa,
    )
    assert [(m.autor, m.estado) for m in mensagens] == [("usuario", "interrompida")]


@pytest.mark.usefixtures("tabela_de_efeitos")
async def test_duplo_clique_executa_uma_vez(cliente_e2e, mundo):
    await mundo.iniciar_worker()
    conversa, cartao = await _pedido(cliente_e2e, mundo)
    respostas = await asyncio.gather(_decidir(cliente_e2e, cartao), _decidir(cliente_e2e, cartao))
    assert sorted(resposta.status_code for resposta in respostas) == [204, 409]
    await _conferir_fim(cliente_e2e, mundo, conversa, cartao, "permitida", 1)


@pytest.mark.usefixtures("tabela_de_efeitos")
async def test_expiracao_fecha_cartao_sem_efeito(cliente_e2e, mundo, monkeypatch):
    monkeypatch.setenv("SORA_PRAZO_APROVACAO_S", "4")
    await mundo.iniciar_worker()
    conversa, cartao = await _pedido(cliente_e2e, mundo)
    await _conferir_fim(cliente_e2e, mundo, conversa, cartao, "expirada", 0)
    resposta = await _decidir(cliente_e2e, cartao)
    assert resposta.status_code == 409, resposta.text
