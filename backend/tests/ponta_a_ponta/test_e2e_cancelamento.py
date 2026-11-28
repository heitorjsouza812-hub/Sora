"""Parar um turno que já chegou à execução libera a fila e encerra o SSE."""

import pytest

from tests.ponta_a_ponta.http import criar_conversa, estado_final_da_fila, ler_ate, sql

pytestmark = [pytest.mark.integracao, pytest.mark.asyncio]


async def test_parar_em_andamento(cliente_e2e, mundo):
    await mundo.iniciar_worker()
    conversa = await criar_conversa(cliente_e2e, "Responda depois [lento:10]")
    eventos = await ler_ate(
        cliente_e2e,
        conversa,
        lambda evento: evento.nome == "passo" and evento.dados["tipo"] == "prompt",
    )
    resposta = await cliente_e2e.post(f"/v1/conversas/{conversa}/parar")
    assert resposta.status_code == 202, resposta.text
    fim = await ler_ate(
        cliente_e2e, conversa, lambda evento: evento.nome == "mensagem.fim", cursor=eventos[-1].id
    )
    assert fim[-1].dados["estado"] == "interrompida"
    pedido = await sql(
        mundo,
        "select estado from mensagens where conversa_id = :id and autor = 'usuario'",
        id=conversa,
    )
    assert pedido[0].estado == "interrompida"
    assert await estado_final_da_fila(mundo, conversa) == "cancelado"
