"""Agenda das rotinas: execuções previstas e o feed iCalendar, sem banco."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.modelos.tabelas import Rotina
from app.rotinas import calendario

AGORA = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def _rotina(**campos: object) -> Rotina:
    base: dict[str, object] = {
        "id": uuid4(),
        "usuario_id": uuid4(),
        "agente_id": uuid4(),
        "titulo": "Resumo",
        "pedido": "Faça o resumo.",
        "tipo": "cron",
        "expressao": "0 9 * * *",
        "fuso": "America/Sao_Paulo",
        "proxima_execucao": datetime(2026, 11, 21, 12, 0, tzinfo=UTC),  # 9h em São Paulo
        "ativa": True,
    }
    return Rotina(**{**base, **campos})


def test_cron_diario_no_fuso_da_rotina() -> None:
    r = _rotina()
    instantes = calendario.ocorrencias_da_rotina(r, AGORA, AGORA + timedelta(days=3, minutes=1))
    assert instantes == [
        datetime(2026, 11, 21, 12, 0, tzinfo=UTC),
        datetime(2026, 11, 22, 12, 0, tzinfo=UTC),
        datetime(2026, 11, 23, 12, 0, tzinfo=UTC),
    ]
    # janela que começa depois da próxima execução conta a partir do começo dela
    depois = AGORA + timedelta(days=10)
    instantes = calendario.ocorrencias_da_rotina(r, depois, depois + timedelta(days=1))
    assert instantes == [datetime(2026, 11, 30, 12, 0, tzinfo=UTC)]  # bem no começo: entra


def test_intervalo_unico_e_pausada() -> None:
    intervalo = _rotina(
        tipo="intervalo", expressao=str(6 * 3600), proxima_execucao=AGORA + timedelta(hours=1)
    )
    assert len(calendario.ocorrencias_da_rotina(intervalo, AGORA, AGORA + timedelta(days=1))) == 4
    longe = AGORA + timedelta(days=5)
    pulado = calendario.ocorrencias_da_rotina(intervalo, longe, longe + timedelta(hours=12))
    assert len(pulado) == 2 and all(longe <= i < longe + timedelta(hours=12) for i in pulado)
    unica = _rotina(tipo="unico", expressao=None, proxima_execucao=AGORA + timedelta(hours=3))
    assert calendario.ocorrencias_da_rotina(unica, AGORA, AGORA + timedelta(days=1)) == [
        AGORA + timedelta(hours=3)
    ]
    assert calendario.ocorrencias_da_rotina(unica, AGORA, AGORA + timedelta(hours=1)) == []
    assert calendario.ocorrencias_da_rotina(_rotina(ativa=False), AGORA, AGORA + timedelta(3)) == []


def test_ocorrencias_ordenadas_e_limite_de_dias() -> None:
    a = _rotina(titulo="B")
    b = _rotina(titulo="A", tipo="unico", expressao=None, proxima_execucao=AGORA)
    itens = calendario.ocorrencias([a, b], AGORA, AGORA + timedelta(days=2, minutes=1))
    assert [o.titulo for o in itens] == ["A", "B", "B"]
    assert calendario.ocorrencias([a], AGORA, AGORA) == []
    with pytest.raises(ValueError, match="62"):
        calendario.ocorrencias([a], AGORA, AGORA + timedelta(days=63))
    # cron a cada 5 min não passa do teto por rotina
    rapida = _rotina(expressao="*/5 * * * *", proxima_execucao=AGORA + timedelta(minutes=5))
    assert len(calendario.ocorrencias_da_rotina(rapida, AGORA, AGORA + timedelta(days=60))) == (
        calendario.MAX_POR_ROTINA
    )


def test_ics_escapa_dobra_e_nao_leva_o_pedido() -> None:
    r = _rotina(titulo="Relatório; vendas, semana\nnova " + "x" * 80, pedido="CPF 529.982.247-25")
    [ocorrencia] = calendario.ocorrencias([r], AGORA, AGORA + timedelta(days=1, minutes=1))
    ics = calendario.gerar_ics([(ocorrencia, "Atlas")], AGORA)
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "DTSTART:20261121T120000Z" in ics
    assert f"UID:{r.id}-{int(ocorrencia.quando.timestamp())}@sora" in ics
    assert "Relatório\\; vendas\\, semana\\nnova" in ics
    assert "529.982" not in ics  # o pedido nunca vai para o feed
    assert "Rotina de Atlas na Sora." in ics
    assert all(len(linha.encode()) <= 75 for linha in ics.split("\r\n"))
    desdobrado = ics.replace("\r\n ", "")
    assert "x" * 80 in desdobrado
