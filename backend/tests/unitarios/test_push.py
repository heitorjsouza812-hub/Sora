"""Notificação no celular (Web Push), sem banco: endereços aceitos, chaves VAPID que funcionam de
verdade, configuração e o aviso de pedido novo (uma vez por pedido)."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import fakeredis
import pytest

from app import push
from app.core.config import Configuracao, obter_configuracao


@pytest.mark.parametrize(
    ("endpoint", "aceito"),
    [
        ("https://fcm.googleapis.com/fcm/send/abc", True),
        ("https://updates.push.services.mozilla.com/wpush/v2/abc", True),
        ("https://web.push.apple.com/QGv", True),
        ("https://db5p.notify.windows.com/w/?token=x", True),
        ("http://fcm.googleapis.com/fcm/send/abc", False),  # sem TLS
        ("https://fcm.googleapis.com:8443/x", False),
        ("https://169.254.169.254/latest/meta-data", False),  # rede interna
        ("https://localhost/x", False),
        ("https://evilnotify.windows.com.atacante.com/x", False),
        ("https://atacante.com/fcm.googleapis.com", False),
    ],
)
def test_so_servicos_de_push_conhecidos(endpoint: str, aceito: bool) -> None:
    assert push.endpoint_permitido(endpoint) is aceito


def _b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def test_chaves_geradas_assinam_e_cifram_de_verdade() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from py_vapid import Vapid02
    from pywebpush import WebPusher

    publica, privada = push.gerar_chaves()
    assert len(_b64(publica)) == 65 and _b64(publica)[0] == 4  # ponto não comprimido
    assert len(_b64(privada)) == 32
    # o servidor assina o JWT VAPID com a privada
    cabecalhos = Vapid02.from_string(privada).sign(
        {"sub": "mailto:a@b.com", "aud": "https://fcm.googleapis.com"}
    )
    assert cabecalhos["Authorization"].startswith("vapid t=")
    # e cifra a carga para as chaves do navegador (aes128gcm)
    navegador = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    inscricao = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/x",
        "keys": {
            "p256dh": base64.urlsafe_b64encode(navegador).rstrip(b"=").decode(),
            "auth": base64.urlsafe_b64encode(b"0123456789abcdef").rstrip(b"=").decode(),
        },
    }
    cifrado = WebPusher(inscricao).encode(b'{"titulo": "x"}', content_encoding="aes128gcm")
    assert b"titulo" not in cifrado["body"]


def test_configuracao_exige_par_e_contato() -> None:
    base: dict[str, Any] = {"ambiente": "teste"}
    assert not Configuracao(**base).push_ligado
    with pytest.raises(ValueError, match="duas chaves"):
        Configuracao(**base, vapid_chave_publica="x")
    with pytest.raises(ValueError, match="VAPID_CONTATO"):
        Configuracao(**base, vapid_chave_publica="x", vapid_chave_privada="y")
    ligado = Configuracao(
        **base, vapid_chave_publica="x", vapid_chave_privada="y", vapid_contato="mailto:a@b.com"
    )
    assert ligado.push_ligado


async def test_aviso_sai_uma_vez_por_pedido_e_so_com_push_ligado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = fakeredis.aioredis.FakeRedis()
    pedidos = [
        SimpleNamespace(id=uuid4(), tipo="aprovacao", agente_id=uuid4(), grupo_id=None),
        SimpleNamespace(id=uuid4(), tipo="pergunta", agente_id=None, grupo_id=uuid4()),
    ]
    fila: list[dict[str, Any]] = []

    async def enfileirar(job: str, **args: Any) -> None:
        fila.append({"job": job, **args})

    monkeypatch.setattr("workers.fila.enfileirar", enfileirar)
    assert await push.avisar_pedidos_novos(redis, uuid4(), pedidos) == 0  # desligado
    monkeypatch.setenv("VAPID_CHAVE_PUBLICA", "x")
    monkeypatch.setenv("VAPID_CHAVE_PRIVADA", "y")
    monkeypatch.setenv("VAPID_CONTATO", "mailto:a@b.com")
    obter_configuracao.cache_clear()
    usuario = uuid4()
    assert await push.avisar_pedidos_novos(redis, usuario, pedidos) == 2
    assert await push.avisar_pedidos_novos(redis, usuario, pedidos) == 0  # já avisados
    assert [f["tipo"] for f in fila] == ["aprovacao", "pergunta"]
    assert fila[0]["job"] == "enviar_push_do_pedido"
    assert fila[0]["agente_id"] == str(pedidos[0].agente_id) and fila[0]["grupo_id"] is None
