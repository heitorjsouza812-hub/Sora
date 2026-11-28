"""O prazo interno fecha a fila e entrega aviso pelo SSE."""

import pytest

from tests.ponta_a_ponta.http import criar_conversa, estado_final_da_fila, ler_ate

pytestmark = [pytest.mark.integracao, pytest.mark.asyncio]


async def test_prazo_do_turno_deixa_estado_final(cliente_e2e, mundo, monkeypatch):
    monkeypatch.setenv("SORA_PRAZO_TURNO_S", "3")
    await mundo.iniciar_worker()
    conversa = await criar_conversa(cliente_e2e, "Responda depois [lento:10]")
    eventos = await ler_ate(cliente_e2e, conversa, lambda evento: evento.nome == "mensagem.fim")
    resposta = "".join(
        evento.dados["texto"] for evento in eventos if evento.nome == "mensagem.delta"
    )
    assert "O tempo deste turno acabou" in resposta
    assert await estado_final_da_fila(mundo, conversa) == "falhou"
