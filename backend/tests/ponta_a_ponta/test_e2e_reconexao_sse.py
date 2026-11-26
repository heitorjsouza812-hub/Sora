"""Reconectar pelo cursor entrega a cauda do turno sem repetir a execução."""

import asyncio
from importlib import import_module

import pytest

from tests.ponta_a_ponta.http import criar_conversa, estado_final_da_fila, ler_ate, sql

pytestmark = [pytest.mark.integracao, pytest.mark.asyncio]


@pytest.fixture
def liberar_fim_da_resposta(monkeypatch):
    """Retém a publicação do fim até o primeiro cliente fechar o socket."""
    modulo = import_module("app.ferramentas.falar")
    publicar = modulo.publicar_evento
    desconectado = asyncio.Event()

    async def publicar_apos_desconexao(redis, evento, *ids):
        if evento.evento == "mensagem.fim":
            await desconectado.wait()
        return await publicar(redis, evento, *ids)

    monkeypatch.setattr(modulo, "publicar_evento", publicar_apos_desconexao)
    return desconectado.set


async def test_reconecta_sem_repetir_eventos_ou_turno(mundo, cliente_e2e, liberar_fim_da_resposta):
    await mundo.iniciar_worker()
    conversa = await criar_conversa(cliente_e2e, "Olá, Sora!")

    def fim(evento):
        return evento.nome == "mensagem.fim"

    try:
        primeira_conexao = await ler_ate(
            cliente_e2e, conversa, lambda evento: evento.nome == "mensagem.delta"
        )
    finally:
        # ler_ate fecha a conexão HTTP antes de devolver o cursor.
        liberar_fim_da_resposta()

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
    assert (
        "".join(evento.dados["texto"] for evento in completos if evento.nome == "mensagem.delta")
        == resposta.conteudo
    )
    historico = await cliente_e2e.get(f"/v1/conversas/{conversa}/mensagens")
    assert historico.status_code == 200, historico.text
    assert await estado_final_da_fila(mundo, conversa) == "concluido"
