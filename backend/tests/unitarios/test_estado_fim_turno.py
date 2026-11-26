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
