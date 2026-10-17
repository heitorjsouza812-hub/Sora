"""Canais de mensagem fora do app (fase 3): a mesma Sora, com as mesmas conversas, falando por
outro aplicativo. Hoje: Telegram (``telegram.py``).

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``messaging-platforms.ts``,
``messaging-delivery.ts``, ``messaging-context.ts`` e ``core/src/messaging-prompts.ts``.
O Rakazo usa um SDK de terceiros; aqui a Bot API do Telegram é chamada direto pelo ``httpx``.

Novos canais (WhatsApp Cloud API, Discord…) seguem o mesmo formato: conferir a origem do
webhook, converter em ``MensagemRecebida``, responder em texto simples cortado no limite do
canal.
"""

from __future__ import annotations

from dataclasses import dataclass

INSTRUCAO_CANAL = (
    "Esta conversa chega por um aplicativo de mensagens, não pelo app da Sora. Responda curto, em "
    "texto simples: sem tabelas, sem títulos em Markdown e sem blocos de código longos. Cartões de "
    "pergunta e de aprovação não aparecem aqui: faça a pergunta em texto com as opções numeradas. "
    "Para entregas grandes, diga que ficaram no app da Sora."
)


@dataclass(frozen=True, slots=True)
class MensagemRecebida:
    canal: str
    chat_id: str
    remetente_id: str
    texto: str
    mensagem_id: str
    nome_remetente: str = ""
