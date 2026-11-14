"""Verificação de origem dos webhooks (obrigatória): Slack e Meta (WhatsApp).

Tudo em tempo constante. Segredo vazio nunca autentica.
"""

from __future__ import annotations

import hashlib
import hmac
import time

JANELA_SLACK_SEGUNDOS = 5 * 60


def assinatura_slack(segredo: str, corpo: bytes, timestamp: str) -> str:
    base = b"v0:" + timestamp.encode() + b":" + corpo
    return "v0=" + hmac.new(segredo.encode(), base, hashlib.sha256).hexdigest()


def slack_autentico(
    segredo: str,
    corpo: bytes,
    timestamp: str | None,
    assinatura: str | None,
    *,
    agora: float | None = None,
) -> bool:
    """``X-Slack-Signature`` = ``v0=`` + HMAC-SHA256 de ``v0:{timestamp}:{corpo}``; pedido com
    mais de 5 minutos de diferença do relógio é recusado (repetição de pedido antigo)."""
    if not segredo or not timestamp or not assinatura:
        return False
    try:
        instante = int(timestamp)
    except ValueError:
        return False
    if abs((agora if agora is not None else time.time()) - instante) > JANELA_SLACK_SEGUNDOS:
        return False
    esperada = assinatura_slack(segredo, corpo, timestamp)
    return hmac.compare_digest(esperada.encode(), assinatura.encode())


def assinatura_meta(app_secret: str, corpo: bytes) -> str:
    return "sha256=" + hmac.new(app_secret.encode(), corpo, hashlib.sha256).hexdigest()


def meta_autentico(app_secret: str, corpo: bytes, assinatura: str | None) -> bool:
    """``X-Hub-Signature-256`` = ``sha256=`` + HMAC-SHA256 do corpo cru com o App Secret."""
    if not app_secret or not assinatura:
        return False
    return hmac.compare_digest(assinatura_meta(app_secret, corpo).encode(), assinatura.encode())


def handshake_meta_valido(verify_token: str, modo: str | None, token_recebido: str | None) -> bool:
    """GET de verificação do webhook: ``hub.mode=subscribe`` e ``hub.verify_token`` igual."""
    if not verify_token or modo != "subscribe" or not token_recebido:
        return False
    return hmac.compare_digest(verify_token.encode(), token_recebido.encode())
