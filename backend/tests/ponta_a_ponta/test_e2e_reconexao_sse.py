"""Reconectar pelo cursor entrega a cauda do turno sem repetir a execução."""

import pytest

from tests.ponta_a_ponta.http import criar_conversa, ler_ate, sql

pytestmark = [pytest.mark.integracao, pytest.mark.asyncio]


async def test_reconecta_sem_repetir_eventos_ou_turno(mundo, cliente_e2e):
    conversa = await criar_conversa(cliente_e2e, "Olá, Sora!")

    def fim(evento):
        return evento.nome == "mensagem.fim"

    primeira_conexao = await ler_ate(
        cliente_e2e, conversa, lambda evento: evento.nome == "roteamento"
    )
    await mundo.iniciar_worker()
    retomada = await ler_ate(cliente_e2e, conversa, fim, cursor=primeira_conexao[-1].id)
    completos = await ler_ate(cliente_e2e, conversa, fim)

    assert retomada
    assert primeira_conexao + retomada == completos
    assert len({evento.id for evento in completos}) == len(completos)
    historico = await cliente_e2e.get(f"/v1/conversas/{conversa}/mensagens")
    assert historico.status_code == 200, historico.text
    mensagens = await sql(
        mundo,
        "select id, autor from mensagens where conversa_id = :id and visivel",
        id=conversa,
    )
    assert len(mensagens) == 2
    assert sum(mensagem.autor == "usuario" for mensagem in mensagens) == 1
    id_final = completos[-1].dados["mensagem_id"]
    assert sum(str(mensagem.id) == id_final for mensagem in mensagens) == 1
