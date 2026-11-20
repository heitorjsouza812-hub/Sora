"""Envio de e-mail transacional (especificação §8.2, "Envio de e-mail").

Interface própria, como a busca: o resto do código só conhece ``EnviadorEmail`` e
``MensagemEmail``. ``EMAIL_PROVEDOR`` escolhe a implementação:

- ``nenhum`` (padrão): desligado. A recuperação de senha responde 503;
- ``console``: só desenvolvimento e teste. Escreve a mensagem no log, inclusive o link,
  para testar sem servidor de e-mail. A configuração recusa subir com ele em produção;
- ``smtp``: qualquer servidor SMTP (Resend, Amazon SES, Brevo, Google Workspace…), com
  STARTTLS (porta 587) ou SSL (porta 465);
- ``resend``: API HTTP do Resend.

Erros nunca levam a senha do SMTP nem a chave da API na mensagem.
"""

from __future__ import annotations

import asyncio
import html
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr
from typing import TYPE_CHECKING, Literal, Protocol

import httpx

if TYPE_CHECKING:
    from app.core.config import Configuracao

registro = logging.getLogger(__name__)

ProvedorEmail = Literal["nenhum", "console", "smtp", "resend"]
SegurancaSmtp = Literal["starttls", "ssl", "nenhuma"]

PRAZO_ENVIO_S = 20.0
URL_RESEND = "https://api.resend.com/emails"


@dataclass(frozen=True)
class MensagemEmail:
    para: str
    assunto: str
    texto: str
    html: str | None = None


class ErroEnvioEmail(Exception):
    """O provedor recusou ou não respondeu. A mensagem nunca tem segredo."""


class EnviadorEmail(Protocol):
    async def enviar(self, mensagem: MensagemEmail) -> None: ...


class EnviadorConsole:
    """Desenvolvimento: a mensagem vai para o log do processo."""

    async def enviar(self, mensagem: MensagemEmail) -> None:
        registro.info(
            "E-mail (console) para %s — %s\n%s", mensagem.para, mensagem.assunto, mensagem.texto
        )


@dataclass
class EnviadorMemoria:
    """Testes: guarda as mensagens em vez de enviar."""

    enviadas: list[MensagemEmail] = field(default_factory=list)
    falhar: bool = False

    async def enviar(self, mensagem: MensagemEmail) -> None:
        if self.falhar:
            raise ErroEnvioEmail("Falha simulada no envio.")
        self.enviadas.append(mensagem)


def _montar(remetente: str, mensagem: MensagemEmail) -> EmailMessage:
    email = EmailMessage()
    email["From"] = remetente
    email["To"] = mensagem.para
    email["Subject"] = mensagem.assunto
    email.set_content(mensagem.texto)
    if mensagem.html:
        email.add_alternative(mensagem.html, subtype="html")
    return email


@dataclass(frozen=True)
class EnviadorSmtp:
    host: str
    porta: int
    remetente: str
    usuario: str | None = None
    senha: str | None = field(default=None, repr=False)
    seguranca: SegurancaSmtp = "starttls"

    def _enviar_sincrono(self, mensagem: MensagemEmail) -> None:
        contexto = ssl.create_default_context()
        email = _montar(self.remetente, mensagem)
        if self.seguranca == "ssl":
            conexao: smtplib.SMTP = smtplib.SMTP_SSL(
                self.host, self.porta, timeout=PRAZO_ENVIO_S, context=contexto
            )
        else:
            conexao = smtplib.SMTP(self.host, self.porta, timeout=PRAZO_ENVIO_S)
        with conexao:
            if self.seguranca == "starttls":
                conexao.starttls(context=contexto)
            if self.usuario:
                conexao.login(self.usuario, self.senha or "")
            conexao.send_message(email)

    async def enviar(self, mensagem: MensagemEmail) -> None:
        try:
            await asyncio.to_thread(self._enviar_sincrono, mensagem)
        except (smtplib.SMTPException, OSError) as erro:
            # Só o tipo do erro: a resposta do servidor pode ecoar o usuário do SMTP.
            tipo = type(erro).__name__
            raise ErroEnvioEmail(f"O servidor SMTP recusou o envio ({tipo}).") from None


@dataclass(frozen=True)
class EnviadorResend:
    chave: str = field(repr=False)
    remetente: str
    url: str = URL_RESEND

    async def enviar(self, mensagem: MensagemEmail) -> None:
        corpo: dict[str, object] = {
            "from": self.remetente,
            "to": [mensagem.para],
            "subject": mensagem.assunto,
            "text": mensagem.texto,
        }
        if mensagem.html:
            corpo["html"] = mensagem.html
        try:
            async with httpx.AsyncClient(timeout=PRAZO_ENVIO_S) as cliente:
                resposta = await cliente.post(
                    self.url, json=corpo, headers={"Authorization": f"Bearer {self.chave}"}
                )
        except httpx.HTTPError as erro:
            raise ErroEnvioEmail(f"O Resend não respondeu ({type(erro).__name__}).") from None
        if resposta.status_code >= 400:
            raise ErroEnvioEmail(f"O Resend recusou o envio (HTTP {resposta.status_code}).")


def remetente_valido(remetente: str) -> bool:
    """``nao-responda@dominio`` ou ``Sora <nao-responda@dominio>``."""
    _, endereco = parseaddr(remetente)
    local, arroba, dominio = endereco.partition("@")
    return bool(local and arroba and "." in dominio)


def criar_enviador(config: Configuracao) -> EnviadorEmail | None:
    """Enviador do ``EMAIL_PROVEDOR`` (``None`` = desligado). A configuração já validou os campos
    obrigatórios de cada provedor no boot."""
    provedor = config.email_provedor
    if provedor == "console":
        return EnviadorConsole()
    if provedor == "smtp":
        return EnviadorSmtp(
            host=config.smtp_host or "",
            porta=config.smtp_porta,
            remetente=config.email_remetente or "",
            usuario=config.smtp_usuario,
            senha=config.smtp_senha.get_secret_value() if config.smtp_senha else None,
            seguranca=config.smtp_seguranca,
        )
    if provedor == "resend":
        return EnviadorResend(
            chave=config.resend_chave.get_secret_value() if config.resend_chave else "",
            remetente=config.email_remetente or "",
        )
    return None


# ---------- mensagens ----------


def mensagem_redefinicao(para: str, nome: str, link: str, validade_minutos: int) -> MensagemEmail:
    """E-mail com o link de senha nova. Texto simples + HTML mínimo (sem imagem externa)."""
    primeiro_nome = (nome or "").strip().split(" ")[0] or "olá"
    texto = (
        f"Olá, {primeiro_nome}.\n\n"
        "Recebemos um pedido para criar uma senha nova na sua conta da Sora. "
        f"Abra o link abaixo em até {validade_minutos} minutos:\n\n"
        f"{link}\n\n"
        "Se não foi você, ignore este e-mail: a sua senha continua a mesma.\n\n"
        "Sora"
    )
    nome_html = html.escape(primeiro_nome)
    link_html = html.escape(link, quote=True)
    corpo_html = (
        '<div style="font-family:Inter,Arial,sans-serif;font-size:15px;line-height:1.5;'
        'color:#0B0D12;max-width:480px">'
        f"<p>Olá, {nome_html}.</p>"
        "<p>Recebemos um pedido para criar uma senha nova na sua conta da Sora. "
        f"O link vale por {validade_minutos} minutos.</p>"
        f'<p><a href="{link_html}" style="display:inline-block;padding:12px 20px;'
        "border-radius:999px;background:#0B0D12;color:#F2F5FB;text-decoration:none;"
        'font-weight:600">Criar senha nova</a></p>'
        f'<p style="font-size:13px;color:#4B5563">Se o botão não abrir, copie este endereço: '
        f"<br>{link_html}</p>"
        '<p style="font-size:13px;color:#4B5563">Se não foi você, ignore este e-mail: '
        "a sua senha continua a mesma.</p>"
        "<p>Sora</p></div>"
    )
    return MensagemEmail(
        para=para, assunto="Crie uma senha nova na Sora", texto=texto, html=corpo_html
    )
