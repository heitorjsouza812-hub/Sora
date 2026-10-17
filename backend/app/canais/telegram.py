"""Canal Telegram: webhook, vínculo da conta e envio de mensagens pela Bot API.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``messaging-platforms.ts``
(``TELEGRAM_BOT_TOKEN`` + segredo do webhook; só modo webhook, nunca long-poll) e
``messaging-delivery.ts`` (entrega idempotente e cortada no limite do canal).

Fluxo:

1. o usuário pede um código no app (``POST /v1/canais/telegram/vinculo``) e manda
   ``/start CODIGO`` para o bot;
2. o webhook confere o cabeçalho ``X-Telegram-Bot-Api-Secret-Token`` (comparação em tempo
   constante), troca o código pelo usuário e grava o vínculo;
3. depois disso, cada mensagem de texto do chat privado vira uma mensagem na conversa da
   Sora (job ``responder_canal``), e a resposta volta cortada em pedaços de 4.096 caracteres.
"""

from __future__ import annotations

import hmac
import re
import secrets
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx

from app.canais import MensagemRecebida
from app.core.redacao import sanitizar_erro

if TYPE_CHECKING:
    from redis.asyncio import Redis

API = "https://api.telegram.org"
LIMITE_MENSAGEM = 4_096
CABECALHO_SEGREDO = "X-Telegram-Bot-Api-Secret-Token"
VALIDADE_CODIGO_SEGUNDOS = 10 * 60
_ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O e 1/I
_START = re.compile(r"^/start(?:@\w+)?(?:\s+([A-Za-z0-9]{6,16}))?\s*$")


class ErroTelegram(Exception):
    """Falha ao falar com a Bot API (mensagem já sem o token)."""


def webhook_autentico(cabecalho: str | None, segredo: str) -> bool:
    """Confere o segredo do webhook em tempo constante. Segredo vazio nunca autentica."""
    if not segredo or not cabecalho:
        return False
    return hmac.compare_digest(cabecalho.encode(), segredo.encode())


def ler_atualizacao(atualizacao: dict[str, Any]) -> MensagemRecebida | None:
    """Só mensagem de texto nova, em chat privado, de uma pessoa (não bot)."""
    mensagem = atualizacao.get("message")
    if not isinstance(mensagem, dict):
        return None
    chat = mensagem.get("chat") or {}
    remetente = mensagem.get("from") or {}
    texto = mensagem.get("text")
    if chat.get("type") != "private" or remetente.get("is_bot") or not isinstance(texto, str):
        return None
    texto = texto.strip()
    if not texto:
        return None
    return MensagemRecebida(
        canal="telegram",
        chat_id=str(chat.get("id")),
        remetente_id=str(remetente.get("id")),
        texto=texto,
        mensagem_id=str(mensagem.get("message_id")),
        nome_remetente=str(remetente.get("first_name") or ""),
    )


def codigo_do_start(texto: str) -> str | None:
    """``/start ABCD2345`` → ``ABCD2345``."""
    casamento = _START.match(texto.strip())
    return casamento.group(1).upper() if casamento and casamento.group(1) else None


def gerar_codigo(tamanho: int = 8) -> str:
    return "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(tamanho))


def _chave_codigo(codigo: str) -> str:
    return f"canal:telegram:vinculo:{codigo.upper()}"


async def criar_codigo_vinculo(redis: Redis, usuario_id: UUID) -> str:
    """Código de uso único, válido por 10 minutos."""
    for _ in range(5):
        codigo = gerar_codigo()
        if await redis.set(
            _chave_codigo(codigo), str(usuario_id), ex=VALIDADE_CODIGO_SEGUNDOS, nx=True
        ):
            return codigo
    raise ErroTelegram("Não consegui gerar um código livre. Tente de novo.")


async def usar_codigo_vinculo(redis: Redis, codigo: str) -> UUID | None:
    """Troca o código pelo usuário e apaga o código (uso único)."""
    valor = await redis.getdel(_chave_codigo(codigo))
    if not valor:
        return None
    try:
        return UUID(valor.decode() if isinstance(valor, bytes) else str(valor))
    except ValueError:
        return None


_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_NEGRITO = re.compile(r"(\*\*|__)(.+?)\1")
_TITULO = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_CERCA_CODIGO = re.compile(r"```[a-zA-Z0-9_-]*\n?")


def markdown_para_texto(texto: str) -> str:
    """Markdown do agente → texto simples legível no Telegram."""
    texto = _CERCA_CODIGO.sub("", texto)
    texto = _LINK.sub(r"\1 (\2)", texto)
    texto = _NEGRITO.sub(r"\2", texto)
    texto = _TITULO.sub("", texto)
    return texto.strip()


def dividir(texto: str, limite: int = LIMITE_MENSAGEM) -> list[str]:
    """Pedaços de até ``limite`` caracteres, cortando em parágrafo, linha ou espaço."""
    texto = texto.strip()
    pedacos: list[str] = []
    while len(texto) > limite:
        corte = -1
        for separador in ("\n\n", "\n", " "):
            corte = texto.rfind(separador, 0, limite)
            if corte > limite // 3:
                break
        if corte <= 0:
            corte = limite
        pedacos.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip()
    if texto:
        pedacos.append(texto)
    return pedacos


class ClienteTelegram:
    """Chamadas à Bot API. O token nunca aparece em erro nem em log."""

    def __init__(self, token: str, *, cliente: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._cliente = cliente

    async def _chamar(self, metodo: str, dados: dict[str, Any]) -> Any:
        proprio = self._cliente is None
        cliente = self._cliente or httpx.AsyncClient(timeout=15, trust_env=False)
        try:
            resposta = await cliente.post(f"{API}/bot{self._token}/{metodo}", json=dados)
        except httpx.HTTPError as erro:
            raise ErroTelegram(
                f"Falha ao falar com o Telegram: {sanitizar_erro(erro, [self._token])}"
            ) from erro
        finally:
            if proprio:
                await cliente.aclose()
        try:
            corpo = resposta.json()
        except ValueError:
            corpo = {}
        if resposta.status_code >= 400 or not corpo.get("ok"):
            descricao = sanitizar_erro(
                str(corpo.get("description") or resposta.status_code), [self._token]
            )
            raise ErroTelegram(f"O Telegram recusou {metodo}: {descricao}")
        return corpo.get("result")

    async def enviar(self, chat_id: str, texto: str) -> int:
        """Manda o texto em pedaços; devolve quantas mensagens saíram."""
        pedacos = dividir(markdown_para_texto(texto))
        for pedaco in pedacos:
            await self._chamar(
                "sendMessage",
                {"chat_id": chat_id, "text": pedaco, "link_preview_options": {"is_disabled": True}},
            )
        return len(pedacos)

    async def digitando(self, chat_id: str) -> None:
        await self._chamar("sendChatAction", {"chat_id": chat_id, "action": "typing"})

    async def registrar_webhook(self, url: str, segredo: str) -> None:
        """Registra o webhook (só mensagens) com o segredo. ``url`` precisa ser https."""
        if not url.startswith("https://"):
            raise ErroTelegram("O webhook do Telegram precisa ser https.")
        await self._chamar(
            "setWebhook",
            {
                "url": url,
                "secret_token": segredo,
                "allowed_updates": ["message"],
                "drop_pending_updates": True,
            },
        )
