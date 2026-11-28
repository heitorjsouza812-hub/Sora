"""Reconectar pelo cursor entrega a cauda do turno sem repetir a execução."""

import pytest

from tests.ponta_a_ponta.http import criar_conversa, estado_final_da_fila, ler_ate, sql

pytestmark = [pytest.mark.integracao, pytest.mark.asyncio]


async def test_reconecta_sem_repetir_eventos_ou_turno(mundo, cliente_e2e):
    await mundo.iniciar_worker()
    conversa = await criar_conversa(cliente_e2e, "Olá, Sora! [lento:3]")

    def fim(evento):
        return evento.nome == "mensagem.fim"

    # O passo precede a chamada ao modelo lento. ler_ate fecha o SSE ao encontrá-lo.
    primeira_conexao = await ler_ate(
        cliente_e2e,
        conversa,
        lambda evento: evento.nome == "passo" and evento.dados["tipo"] == "prompt",
    )
    assert all(evento.nome not in {"mensagem.delta", "mensagem.fim"} for evento in primeira_conexao)

    assert await estado_final_da_fila(mundo, conversa) == "concluido"
    mensagens = await sql(
        mundo,
        "select id, autor, conteudo from mensagens where conversa_id = :id and visivel",
        id=conversa,
    )
    assert len(mensagens) == 2
    assert sum(mensagem.autor == "usuario" for mensagem in mensagens) == 1
    resposta = next(mensagem for mensagem in mensagens if mensagem.autor == "sora")

    retomada = await ler_ate(cliente_e2e, conversa, fim, cursor=primeira_conexao[-1].id)
    completos = await ler_ate(cliente_e2e, conversa, fim)
    assert primeira_conexao + retomada == completos
    assert len({evento.id for evento in completos}) == len(completos)
    assert retomada[-1].dados["mensagem_id"] == str(resposta.id)
    deltas = [evento.dados["texto"] for evento in retomada if evento.nome == "mensagem.delta"]
    assert deltas
    assert "".join(deltas) == resposta.conteudo
    historico = await cliente_e2e.get(f"/v1/conversas/{conversa}/mensagens")
    assert historico.status_code == 200, historico.text
    assert await estado_final_da_fila(mundo, conversa) == "concluido"
