"""O encerramento da fila conserva a distinção entre cancelar, falhar e concluir."""

from uuid import uuid4

import pytest

from app.filas import ArmazemFilaEmMemoria, FilaAgente, OrigemItem, StatusItem
from workers.equipe import _encerrar_item_fila


@pytest.mark.parametrize(
    ("estado_turno", "estado_final", "motivo"),
    [
        (StatusItem.CANCELADO, StatusItem.CANCELADO, "cancelado_pelo_usuario"),
        (StatusItem.FALHOU, StatusItem.FALHOU, "prazo_do_turno"),
        (None, StatusItem.CONCLUIDO, None),
    ],
)
async def test_fila_grava_o_estado_real_do_turno(estado_turno, estado_final, motivo):
    armazem = ArmazemFilaEmMemoria()
    fila = FilaAgente(armazem)
    agente = uuid4()
    item = await fila.enfileirar(
        usuario_id=uuid4(), agente_id=agente, texto="Pedido", origem=OrigemItem.USUARIO
    )
    await fila.iniciar(item.id, agente)
    await fila.rodando(item.id, agente)
    await _encerrar_item_fila(fila, item, estado_turno)
    encerrado = (await armazem.itens(agente))[0]
    assert encerrado.status is estado_final
    assert encerrado.motivo == motivo
    assert encerrado.terminado_em is not None


async def test_cancelamento_tardio_preserva_o_proximo_item_na_mesma_pista():
    armazem = ArmazemFilaEmMemoria()
    fila = FilaAgente(armazem)
    usuario, agente = uuid4(), uuid4()
    antigo = await fila.enfileirar(
        usuario_id=usuario, agente_id=agente, texto="Pedido antigo", origem=OrigemItem.USUARIO
    )
    novo = await fila.enfileirar(
        usuario_id=usuario, agente_id=agente, texto="Pedido novo", origem=OrigemItem.USUARIO
    )
    assert antigo.pista == novo.pista
    await fila.iniciar(antigo.id, agente)
    await fila.rodando(antigo.id, agente)
    assert [item.id for item in await fila.recuperar_apos_queda()] == [antigo.id]
    await fila.iniciar(novo.id, agente)
    await fila.rodando(novo.id, agente)

    await _encerrar_item_fila(fila, antigo, StatusItem.CANCELADO)

    itens = {item.id: item for item in await armazem.itens(agente)}
    assert itens[antigo.id].status is StatusItem.INTERROMPIDO
    assert itens[novo.id].status is StatusItem.RODANDO
    assert itens[novo.id].terminado_em is None
