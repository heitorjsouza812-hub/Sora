"""Senha segura no navegador do bot (Onda 2, 2026-11-20; ideia vista no OpenBot, escrita do zero).

O bot chama ``navegador_pedir_senha`` com a ref do campo de senha. Aparece um cartão em "Precisa
de você"; o usuário digita a senha no app e ela segue este caminho:

1. ``POST /v1/navegador/senhas/{cartao}`` guarda a senha **cifrada** (chave mestra, AAD com o
   usuário e o cartão) no Redis, por ``VALIDADE_NO_REDIS``, e decide o cartão como "permitir";
2. o turno do bot retoma; a ferramenta lê e apaga a senha (``GETDEL``) e preenche o campo na
   página, conferindo antes que a aba continua no mesmo site;
3. o modelo recebe só "a senha foi preenchida". O valor nunca entra no histórico do turno, no
   valor de retomada, no rastro do navegador (o motor marca campo de senha) nem em log.

Nada é guardado depois: o login fica nos cookies do perfil do navegador do bot, como antes.
"""

from __future__ import annotations

import base64
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from app.core import seguranca

CHAVE_REDIS = "navegador:senha:{}"
VALIDADE_NO_REDIS_S = 5 * 60
VALIDADE_CARTAO = timedelta(minutes=10)
MAX_CARTOES = 5
MAX_SENHA = 500


def dominio_de(url: str | None) -> str:
    return (urlsplit(url or "").hostname or "").lower()


def aad(usuario_id: UUID, cartao_id: UUID) -> dict[str, Any]:
    return {"usuario_id": usuario_id, "provedor": f"senha-navegador:{cartao_id}"}


async def guardar(redis: Any, usuario_id: UUID, cartao_id: UUID, senha: str) -> None:
    cifrada = seguranca.cifrar_segredo(senha, **aad(usuario_id, cartao_id))
    await redis.set(
        CHAVE_REDIS.format(cartao_id), base64.b64encode(cifrada).decode(), ex=VALIDADE_NO_REDIS_S
    )


async def apagar(redis: Any, cartao_id: UUID) -> None:
    await redis.delete(CHAVE_REDIS.format(cartao_id))


async def ler_e_apagar(redis: Any, usuario_id: UUID, cartao_id: UUID) -> str | None:
    """Lê uma vez só (``GETDEL``). ``None`` = não chegou ou já passou do prazo."""
    bruto = await redis.getdel(CHAVE_REDIS.format(cartao_id))
    if not bruto:
        return None
    texto = bruto.decode() if isinstance(bruto, bytes) else str(bruto)
    return seguranca.decifrar_segredo(base64.b64decode(texto), **aad(usuario_id, cartao_id))
