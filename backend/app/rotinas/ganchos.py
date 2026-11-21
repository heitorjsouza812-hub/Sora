"""Webhook das rotinas (Onda 2, 2026-11-20; ideia vista no OpenBot, escrita do zero).

Outro serviço (loja, formulário, pagamento) chama ``POST /v1/ganchos/{rota}`` e a rotina roda com
os dados recebidos. Segue o padrão **Standard Webhooks** (standardwebhooks.com), que muitos
serviços já falam:

- cabeçalhos ``webhook-id``, ``webhook-timestamp`` e ``webhook-signature``;
- assinatura ``v1,<base64>`` = HMAC-SHA256 de ``"{id}.{timestamp}.{corpo}"`` com a chave que vem
  depois de ``whsec_`` no segredo (base64). Pode vir mais de uma, separadas por espaço;
- horário com tolerância de 5 minutos (contra reenvio de uma chamada antiga);
- o mesmo ``webhook-id`` duas vezes não roda de novo (responde 200, como pede o padrão).

Regras nossas: a rota da URL é aleatória (ninguém adivinha), o segredo fica cifrado com a chave
mestra, o corpo nunca é gravado (só tamanho e tipo de evento), limite de chamadas por gancho, e os
dados entram no bot **cercados como dado externo** numa rotina sem supervisão (só ferramentas
seguras): o que chega pelo webhook nunca vira instrução.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import seguranca
from app.core.redis import verificar_limite
from app.modelos.tabelas import EntregaGancho, GanchoRotina, Rotina, RotinaExecucao

TOLERANCIA = timedelta(minutes=5)
MAX_CORPO_BYTES = 256 * 1024
MAX_DADOS_PARA_O_BOT = 20_000
MAX_TIPOS_EVENTO = 20
LIMITE_POR_MINUTO = (10, 60)
LIMITE_POR_HORA = (60, 60 * 60)
RETENCAO_ENTREGAS = timedelta(days=30)
PREFIXO_SEGREDO = "whsec_"

Resultado = Literal["aceita", "ignorada", "repetida"]


class ErroGancho(Exception):
    """Recusa da chamada; ``status`` é o código HTTP e ``detalhe`` vai na resposta."""

    def __init__(self, status: int, detalhe: str, espera: int | None = None) -> None:
        super().__init__(detalhe)
        self.status = status
        self.detalhe = detalhe
        self.espera = espera


@dataclass(frozen=True)
class Recebida:
    resultado: Resultado
    execucao_id: UUID | None = None


# ---------- segredo e assinatura (funções puras) ----------


def novo_segredo() -> str:
    return PREFIXO_SEGREDO + base64.b64encode(secrets.token_bytes(32)).decode()


def nova_rota() -> str:
    return secrets.token_urlsafe(24)


def _chave(segredo: str) -> bytes:
    return base64.b64decode(segredo.removeprefix(PREFIXO_SEGREDO))


def assinar(segredo: str, mensagem_id: str, timestamp: int, corpo: bytes) -> str:
    """Valor de ``webhook-signature`` para o corpo (usado no "Enviar teste" e nos testes)."""
    conteudo = f"{mensagem_id}.{timestamp}.".encode() + corpo
    digest = hmac.new(_chave(segredo), conteudo, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def assinatura_valida(
    segredo: str, cabecalhos: Mapping[str, str], corpo: bytes, agora: datetime
) -> bool:
    """Confere id, horário (±5 min) e pelo menos uma assinatura ``v1`` (comparação constante)."""
    mensagem_id = (cabecalhos.get("webhook-id") or "").strip()
    bruto_ts = (cabecalhos.get("webhook-timestamp") or "").strip()
    assinaturas = (cabecalhos.get("webhook-signature") or "").split()
    if not mensagem_id or not bruto_ts.isdigit() or not assinaturas:
        return False
    timestamp = int(bruto_ts)
    if abs(agora - datetime.fromtimestamp(timestamp, UTC)) > TOLERANCIA:
        return False
    esperada = assinar(segredo, mensagem_id, timestamp, corpo).encode()
    return any(
        assinatura.startswith("v1,") and hmac.compare_digest(assinatura.encode(), esperada)
        for assinatura in assinaturas
    )


def tipo_do_evento(corpo: bytes) -> str | None:
    """``type`` do JSON (o campo do padrão), se houver."""
    try:
        dados = json.loads(corpo)
    except (ValueError, UnicodeDecodeError):
        return None
    tipo = dados.get("type") if isinstance(dados, dict) else None
    return str(tipo)[:120] if isinstance(tipo, (str, int)) else None


def normalizar_tipos(tipos: list[str]) -> list[str]:
    limpos = sorted({t.strip()[:120] for t in tipos if t and t.strip()})
    if len(limpos) > MAX_TIPOS_EVENTO:
        raise ValueError(f"Use no máximo {MAX_TIPOS_EVENTO} tipos de evento.")
    return limpos


def dados_para_o_bot(corpo: bytes) -> str:
    """O corpo como texto para o bot: JSON bonito quando dá, cortado no limite."""
    texto = corpo.decode("utf-8", errors="replace")
    try:
        texto = json.dumps(json.loads(texto), ensure_ascii=False, indent=2)
    except ValueError:
        pass
    if len(texto) > MAX_DADOS_PARA_O_BOT:
        texto = texto[:MAX_DADOS_PARA_O_BOT] + "\n[… cortado: os dados passaram do limite]"
    return texto


def _aad(gancho: GanchoRotina) -> dict[str, object]:
    return {"usuario_id": gancho.usuario_id, "provedor": f"gancho:{gancho.id}"}


def segredo_de(gancho: GanchoRotina) -> str:
    return seguranca.decifrar_segredo(gancho.segredo_cifrado, **_aad(gancho))


# ---------- gestão (rotas autenticadas) ----------


async def gancho_da_rotina(sessao: AsyncSession, rotina_id: UUID) -> GanchoRotina | None:
    return await sessao.scalar(select(GanchoRotina).where(GanchoRotina.rotina_id == rotina_id))


async def criar_ou_trocar_segredo(
    sessao: AsyncSession, rotina: Rotina, tipos_evento: list[str] | None = None
) -> tuple[GanchoRotina, str]:
    """Cria o webhook da rotina ou, se já existe, troca o segredo (o antigo para de valer na
    hora). A rota continua a mesma. Devolve o segredo novo (mostrado uma vez)."""
    segredo = novo_segredo()
    gancho = await gancho_da_rotina(sessao, rotina.id)
    if gancho is None:
        gancho = GanchoRotina(
            id=uuid4(),
            rotina_id=rotina.id,
            usuario_id=rotina.usuario_id,
            rota=nova_rota(),
            segredo_cifrado=b"",
            tipos_evento=normalizar_tipos(tipos_evento or []),
        )
        sessao.add(gancho)
    elif tipos_evento is not None:
        gancho.tipos_evento = normalizar_tipos(tipos_evento)
    gancho.segredo_cifrado = seguranca.cifrar_segredo(segredo, **_aad(gancho))
    await sessao.flush()
    return gancho, segredo


async def entregas_recentes(
    sessao: AsyncSession, gancho_id: UUID, limite: int = 20
) -> list[EntregaGancho]:
    return list(
        (
            await sessao.scalars(
                select(EntregaGancho)
                .where(EntregaGancho.gancho_id == gancho_id)
                .order_by(EntregaGancho.recebida_em.desc())
                .limit(limite)
            )
        ).all()
    )


async def apagar_entregas_vencidas(sessao: AsyncSession, agora: datetime | None = None) -> int:
    limite = (agora or datetime.now(UTC)) - RETENCAO_ENTREGAS
    resultado = await sessao.execute(
        delete(EntregaGancho).where(EntregaGancho.recebida_em < limite)
    )
    await sessao.commit()
    return resultado.rowcount or 0


# ---------- recebimento (rota pública) ----------


async def receber(
    sessao: AsyncSession,
    redis: Redis,
    rota: str,
    cabecalhos: Mapping[str, str],
    corpo: bytes,
    agora: datetime | None = None,
) -> tuple[Recebida, GanchoRotina | None]:
    """Confere a chamada e, se for nova e do tipo certo, cria a execução da rotina (sem commit).

    A ordem é pensada para gastar pouco com chamadas falsas: tamanho, rota, limite, assinatura
    e só depois banco. Quem chama põe o job na fila depois do commit."""
    agora = agora or datetime.now(UTC)
    if len(corpo) > MAX_CORPO_BYTES:
        raise ErroGancho(413, "Corpo grande demais (máximo 256 KB).")
    gancho = await sessao.scalar(select(GanchoRotina).where(GanchoRotina.rota == rota))
    if gancho is None or not gancho.ativo:
        raise ErroGancho(404, "Webhook não encontrado.")
    for chave, limite in ((":minuto", LIMITE_POR_MINUTO), (":hora", LIMITE_POR_HORA)):
        espera = await verificar_limite(redis, f"gancho:{gancho.id}{chave}", *limite)
        if espera:
            raise ErroGancho(429, "Muitas chamadas para este webhook.", espera)
    if not assinatura_valida(segredo_de(gancho), cabecalhos, corpo, agora):
        raise ErroGancho(401, "Assinatura inválida ou fora do horário.")

    tipo = tipo_do_evento(corpo)
    aceita = not gancho.tipos_evento or (tipo is not None and tipo in gancho.tipos_evento)
    entrega = EntregaGancho(
        id=uuid4(),
        gancho_id=gancho.id,
        usuario_id=gancho.usuario_id,
        mensagem_id=cabecalhos["webhook-id"].strip()[:200],
        tipo_evento=tipo,
        status="aceita" if aceita else "ignorada",
        tamanho=len(corpo),
        recebida_em=agora,
    )
    try:
        async with sessao.begin_nested():
            sessao.add(entrega)
            await sessao.flush()
    except IntegrityError:
        return Recebida("repetida"), gancho
    gancho.ultimo_recebido_em = agora
    if not aceita:
        return Recebida("ignorada"), gancho
    execucao = RotinaExecucao(
        id=uuid4(),
        rotina_id=gancho.rotina_id,
        usuario_id=gancho.usuario_id,
        iniciada_em=agora,
        origem="webhook",
    )
    sessao.add(execucao)
    entrega.execucao_id = execucao.id
    await sessao.flush()
    return Recebida("aceita", execucao.id), gancho
