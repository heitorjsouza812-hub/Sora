"""Webhook das rotinas: assinatura Standard Webhooks e regras puras, sem banco.

O caminho com PostgreSQL e Redis (receber, repetida, filtro, limite, rotas) está em
``tests/integracao/test_ganchos_rotina.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.rotinas import ganchos

AGORA = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def _cabecalhos(segredo: str, corpo: bytes, quando: datetime = AGORA, msg: str = "msg_1") -> dict:
    ts = int(quando.timestamp())
    return {
        "webhook-id": msg,
        "webhook-timestamp": str(ts),
        "webhook-signature": ganchos.assinar(segredo, msg, ts, corpo),
    }


def test_assinatura_bate_com_o_exemplo_oficial_do_padrao() -> None:
    # Vetor de teste das bibliotecas de referência do Standard Webhooks. O texto vai partido para
    # o bloqueio de segredos do GitHub não confundir com um segredo de webhook da Stripe.
    assinatura = ganchos.assinar(
        "whsec_" + "MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw",
        "msg_p5jXN8AQM9LWM0D4loKWxJek",
        1614265330,
        b'{"test": 2432232314}',
    )
    assert assinatura == "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="


def test_assinatura_valida_e_recusas() -> None:
    segredo = ganchos.novo_segredo()
    corpo = b'{"type": "pedido.pago"}'
    assert segredo.startswith("whsec_")
    assert ganchos.assinatura_valida(segredo, _cabecalhos(segredo, corpo), corpo, AGORA)
    # corpo trocado, segredo errado, sem cabeçalho
    assert not ganchos.assinatura_valida(segredo, _cabecalhos(segredo, corpo), b"{}", AGORA)
    outro = ganchos.novo_segredo()
    assert not ganchos.assinatura_valida(segredo, _cabecalhos(outro, corpo), corpo, AGORA)
    assert not ganchos.assinatura_valida(segredo, {}, corpo, AGORA)
    # horário: 5 min de tolerância para os dois lados
    velho = _cabecalhos(segredo, corpo, AGORA - timedelta(minutes=5, seconds=1))
    assert not ganchos.assinatura_valida(segredo, velho, corpo, AGORA)
    futuro = _cabecalhos(segredo, corpo, AGORA + timedelta(minutes=6))
    assert not ganchos.assinatura_valida(segredo, futuro, corpo, AGORA)
    no_limite = _cabecalhos(segredo, corpo, AGORA - timedelta(minutes=5))
    assert ganchos.assinatura_valida(segredo, no_limite, corpo, AGORA)


def test_aceita_uma_entre_varias_assinaturas_e_ignora_versao_desconhecida() -> None:
    segredo = ganchos.novo_segredo()
    corpo = b"{}"
    cab = _cabecalhos(segredo, corpo)
    boa = cab["webhook-signature"]
    cab["webhook-signature"] = f"v1,AAAA {boa}"
    assert ganchos.assinatura_valida(segredo, cab, corpo, AGORA)
    cab["webhook-signature"] = boa.replace("v1,", "v2,")
    assert not ganchos.assinatura_valida(segredo, cab, corpo, AGORA)


def test_tipo_do_evento_e_filtro() -> None:
    assert ganchos.tipo_do_evento(b'{"type": "pedido.pago", "data": {}}') == "pedido.pago"
    assert ganchos.tipo_do_evento(b"[1, 2]") is None
    assert ganchos.tipo_do_evento(b"nao e json") is None
    assert ganchos.normalizar_tipos([" b ", "a", "b", ""]) == ["a", "b"]
    with pytest.raises(ValueError):
        ganchos.normalizar_tipos([f"t{i}" for i in range(ganchos.MAX_TIPOS_EVENTO + 1)])


def test_dados_para_o_bot_formata_json_e_corta_no_limite() -> None:
    assert ganchos.dados_para_o_bot(b'{"a":1}') == '{\n  "a": 1\n}'
    assert ganchos.dados_para_o_bot("ção".encode()) == "ção"
    grande = ganchos.dados_para_o_bot(b"x" * (ganchos.MAX_DADOS_PARA_O_BOT + 50))
    assert grande.endswith("[… cortado: os dados passaram do limite]")
    assert len(grande) < ganchos.MAX_DADOS_PARA_O_BOT + 60


def test_rota_e_segredo_sao_aleatorios() -> None:
    assert len({ganchos.nova_rota() for _ in range(50)}) == 50
    assert len(ganchos.nova_rota()) >= 32
