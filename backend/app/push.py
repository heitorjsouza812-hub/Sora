"""Notificação no celular do "Precisa de você" (Web Push, Onda 2, 2026-11-20).

Como funciona:

- o app (PWA) pede permissão, inscreve o aparelho no serviço de push do navegador e manda a
  inscrição para ``/v1/push/inscricoes``;
- quando aparece um pedido NOVO em "Precisa de você" (``app/atencao.py``), o worker envia uma
  notificação para cada aparelho da conta. Um pedido avisa uma vez só (marca no Redis);
- a notificação diz só quem precisa ("Atlas precisa de você") e abre o cartão: nada do conteúdo
  do pedido passa pelos servidores de push (Google, Mozilla, Apple, Microsoft);
- aparelho que o serviço diz que não existe mais (404/410) é apagado.

Segurança: o endereço de entrega vem do navegador, então só aceitamos ``https`` nos serviços de
push conhecidos (senão um cliente malicioso faria o worker chamar a rede interna). As chaves
VAPID ficam na configuração (``VAPID_CHAVE_PUBLICA``/``_PRIVADA``).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.tabelas import Agente, CanalEquipe, InscricaoPush

registro = logging.getLogger(__name__)

MAX_INSCRICOES = 10
VALIDADE_MARCA_PEDIDO_S = 7 * 24 * 3600
TTL_PUSH_S = 12 * 3600
PRAZO_ENVIO_S = 15.0

_HOSTS_EXATOS = frozenset(
    {"fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com"}
)
_SUFIXOS = (".push.services.mozilla.com", ".notify.windows.com", ".push.apple.com")
_HOSTS_APPLE = frozenset({"web.push.apple.com"})


class ChavesInscricao(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class InscricaoEntrada(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1_000)
    keys: ChavesInscricao


class ErroInscricao(ValueError):
    """Endereço de push que não é de um serviço conhecido."""


def endpoint_permitido(endpoint: str) -> bool:
    partes = urlsplit(endpoint)
    host = (partes.hostname or "").lower()
    if partes.scheme != "https" or not host or partes.port not in (None, 443):
        return False
    return host in _HOSTS_EXATOS or host in _HOSTS_APPLE or host.endswith(_SUFIXOS)


def gerar_chaves() -> tuple[str, str]:
    """(pública, privada) em base64url, prontas para o ``.env``."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    privada = ec.generate_private_key(ec.SECP256R1())
    bruta = privada.private_numbers().private_value.to_bytes(32, "big")
    publica = privada.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    def b64(dados: bytes) -> str:
        return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()

    return b64(publica), b64(bruta)


# ---------- inscrições ----------


async def salvar_inscricao(
    sessao: AsyncSession, usuario_id: UUID, dados: InscricaoEntrada, aparelho: str | None
) -> InscricaoPush:
    if not endpoint_permitido(dados.endpoint):
        raise ErroInscricao("Esse endereço de notificação não é de um serviço de push conhecido.")
    existente = await sessao.scalar(
        select(InscricaoPush).where(InscricaoPush.endpoint == dados.endpoint)
    )
    if existente is not None:  # o mesmo aparelho (ou outra conta nele): fica com quem inscreveu
        existente.usuario_id = usuario_id
        existente.p256dh, existente.auth = dados.keys.p256dh, dados.keys.auth
        existente.aparelho = aparelho
        await sessao.flush()
        return existente
    atuais = list(
        (
            await sessao.scalars(
                select(InscricaoPush)
                .where(InscricaoPush.usuario_id == usuario_id)
                .order_by(InscricaoPush.criada_em)
            )
        ).all()
    )
    for velha in atuais[: max(0, len(atuais) - MAX_INSCRICOES + 1)]:
        await sessao.delete(velha)
    nova = InscricaoPush(
        usuario_id=usuario_id,
        endpoint=dados.endpoint,
        p256dh=dados.keys.p256dh,
        auth=dados.keys.auth,
        aparelho=aparelho,
    )
    sessao.add(nova)
    await sessao.flush()
    return nova


async def apagar_inscricao(sessao: AsyncSession, usuario_id: UUID, endpoint: str) -> None:
    await sessao.execute(
        delete(InscricaoPush).where(
            InscricaoPush.usuario_id == usuario_id, InscricaoPush.endpoint == endpoint
        )
    )


# ---------- envio ----------


@dataclass(frozen=True)
class Envio:
    enviadas: int
    removidas: int


def _enviar_um(inscricao: InscricaoPush, carga: str, chave_privada: str, contato: str) -> int:
    """Manda para um aparelho. Devolve o status HTTP do serviço de push (0 = sem resposta)."""
    from pywebpush import WebPushException, webpush

    try:
        resposta = webpush(
            {
                "endpoint": inscricao.endpoint,
                "keys": {"p256dh": inscricao.p256dh, "auth": inscricao.auth},
            },
            data=carga,
            vapid_private_key=chave_privada,
            vapid_claims={"sub": contato},
            ttl=TTL_PUSH_S,
            timeout=PRAZO_ENVIO_S,
            headers={"Urgency": "high"},
        )
    except WebPushException as erro:
        return getattr(erro.response, "status_code", 0) or 0
    return int(getattr(resposta, "status_code", 201) or 201)


async def enviar_para_usuario(
    sessao: AsyncSession, usuario_id: UUID, carga: dict[str, Any]
) -> Envio:
    """Manda a mesma notificação para todos os aparelhos da conta (sem commit)."""
    from app.core.config import obter_configuracao

    config = obter_configuracao()
    if not config.push_ligado or config.vapid_chave_privada is None:
        return Envio(0, 0)
    inscricoes = list(
        (
            await sessao.scalars(
                select(InscricaoPush).where(InscricaoPush.usuario_id == usuario_id)
            )
        ).all()
    )
    texto = json.dumps(carga, ensure_ascii=False)
    enviadas = removidas = 0
    for inscricao in inscricoes:
        if not endpoint_permitido(inscricao.endpoint):  # gravada antes de uma regra nova
            await sessao.delete(inscricao)
            removidas += 1
            continue
        status = await asyncio.to_thread(
            _enviar_um,
            inscricao,
            texto,
            config.vapid_chave_privada.get_secret_value(),
            config.vapid_contato or "",
        )
        if status in (404, 410):
            await sessao.delete(inscricao)
            removidas += 1
        elif 200 <= status < 300:
            inscricao.ultimo_envio_em = datetime.now(UTC)
            enviadas += 1
        else:
            registro.warning("o serviço de push respondeu %s", status)
    await sessao.flush()
    return Envio(enviadas, removidas)


async def carga_do_pedido(
    sessao: AsyncSession,
    pedido_id: str,
    tipo: str,
    agente_id: UUID | None,
    grupo_id: UUID | None,
) -> dict[str, Any]:
    """Texto genérico (quem precisa e de quê) e o caminho do cartão. Nada do conteúdo."""
    origem = "A Sora"
    if grupo_id is not None:
        nome = await sessao.scalar(select(CanalEquipe.nome).where(CanalEquipe.id == grupo_id))
        origem = f"O grupo {nome}" if nome else "Um grupo"
        caminho = f"/grupos/{grupo_id}"
    elif agente_id is not None:
        nome = await sessao.scalar(select(Agente.nome).where(Agente.id == agente_id))
        origem = nome or "Um bot"
        caminho = f"/bots/{agente_id}"
    else:
        caminho = "/"
    pedido = "tem uma pergunta para você." if tipo == "pergunta" else "precisa da sua aprovação."
    return {
        "titulo": "Precisa de você",
        "corpo": f"{origem} {pedido}",
        "url": f"{caminho}#pedido-{pedido_id}",
        "tag": f"pedido-{pedido_id}",
    }


async def avisar_pedidos_novos(redis: Any, usuario_id: UUID, pedidos: list[Any]) -> int:
    """Põe na fila um aviso por pedido que ainda não foi avisado (marca ``SET NX`` no Redis)."""
    from app.core.config import obter_configuracao

    if not pedidos or not obter_configuracao().push_ligado:
        return 0
    from workers.fila import enfileirar

    novos = 0
    for pedido in pedidos:
        marca = f"push:pedido:{pedido.id}"
        if not await redis.set(marca, "1", nx=True, ex=VALIDADE_MARCA_PEDIDO_S):
            continue
        novos += 1
        await enfileirar(
            "enviar_push_do_pedido",
            id_job=f"push:{pedido.id}",
            usuario_id=str(usuario_id),
            pedido_id=str(pedido.id),
            tipo=pedido.tipo,
            agente_id=str(pedido.agente_id) if pedido.agente_id else None,
            grupo_id=str(pedido.grupo_id) if pedido.grupo_id else None,
        )
    return novos
