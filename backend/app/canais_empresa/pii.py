"""Máscara de dados sensíveis dos canais da empresa.

Roda ANTES de gravar qualquer coisa que veio de um cliente (inclusive a mensagem crua) e de
novo sobre tudo que o modelo extrai. Mascara CPF, CNPJ, cartão de pagamento, senhas, códigos de
verificação e tokens/chaves. Telefone e e-mail do cliente não são mascarados na mensagem (são
dados de contato que a ficha precisa guardar), mas saem do conhecimento da empresa, que nunca
leva dado pessoal (``anonimizar_para_conhecimento``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.core.redacao import limpar_texto_sensivel

CPF_MASCARA = "[CPF]"
CNPJ_MASCARA = "[CNPJ]"
CARTAO_MASCARA = "[cartão]"
SENHA_MASCARA = "[senha]"
TOKEN_MASCARA = "[token]"
CODIGO_MASCARA = "[código]"

_CPF_FORMATADO = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
_CPF_CRU = re.compile(r"(?<![\d.])\d{11}(?![\d.])")
_CNPJ_FORMATADO = re.compile(r"(?<!\d)\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}(?!\d)")
_CNPJ_CRU = re.compile(r"(?<![\d.])\d{14}(?![\d.])")
_CARTAO = re.compile(r"(?<![\d+])(?:\d[ -]?){12,18}\d(?!\d)")
_SENHA = re.compile(
    r"(?i)\b(senha|password|passwd|pin|cvv|cvc|cód(?:igo)?\.? de seguran[cç]a)"
    r"(\s*(?:[:=]|é|e|eh|is|foi|nova)\s*)(\S+)"
)
_CODIGO = re.compile(
    r"(?i)\b(c[oó]digo(?: de (?:verifica[cç][aã]o|acesso|confirma[cç][aã]o))?|token|otp)"
    r"(\s*(?:[:=]|é|e|eh|is)\s*)(\d{4,8})\b"
)
_TOKENS = (
    re.compile(r"\bxox[abprso]-[A-Za-z0-9-]{10,}"),  # Slack
    re.compile(r"\bxapp-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bEAA[A-Za-z0-9]{20,}"),  # Meta / WhatsApp
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{40,}\b"),
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TELEFONE = re.compile(r"(?<![\d.])(?:\+?55[ -]?)?\(?\d{2}\)?[ -]?9?\d{4}[ -]?\d{4}(?![\d-])")


def _digitos(texto: str) -> list[int]:
    return [int(c) for c in texto if c.isdigit()]


def cpf_valido(texto: str) -> bool:
    d = _digitos(texto)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        soma = sum(d[i] * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != d[n]:
            return False
    return True


def cnpj_valido(texto: str) -> bool:
    d = _digitos(texto)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for n in (12, 13):
        soma = sum(d[i] * pesos[i + 13 - n] for i in range(n))
        resto = soma % 11
        if (0 if resto < 2 else 11 - resto) != d[n]:
            return False
    return True


def cartao_valido(texto: str) -> bool:
    """Luhn em 13 a 19 dígitos. Telefone brasileiro com DDI (55 + 10 ou 11 dígitos) não conta."""
    d = _digitos(texto)
    if not 13 <= len(d) <= 19 or len(set(d)) == 1:
        return False
    if d[0] == 5 and d[1] == 5 and len(d) in (12, 13):
        return False
    soma = 0
    for i, digito in enumerate(reversed(d)):
        if i % 2:
            digito *= 2
            if digito > 9:
                digito -= 9
        soma += digito
    return soma % 10 == 0


def mascarar_pii(texto: str) -> str:
    """Mascara CPF, CNPJ, cartão, senha, código de verificação e tokens. Idempotente."""
    if not texto:
        return texto
    texto = _SENHA.sub(lambda m: f"{m.group(1)}{m.group(2)}{SENHA_MASCARA}", texto)
    texto = _CODIGO.sub(lambda m: f"{m.group(1)}{m.group(2)}{CODIGO_MASCARA}", texto)
    texto = _CNPJ_FORMATADO.sub(CNPJ_MASCARA, texto)
    texto = _CNPJ_CRU.sub(lambda m: CNPJ_MASCARA if cnpj_valido(m.group()) else m.group(), texto)
    texto = _CPF_FORMATADO.sub(CPF_MASCARA, texto)
    texto = _CARTAO.sub(lambda m: CARTAO_MASCARA if cartao_valido(m.group()) else m.group(), texto)
    texto = _CPF_CRU.sub(lambda m: CPF_MASCARA if cpf_valido(m.group()) else m.group(), texto)
    for padrao in _TOKENS:
        texto = padrao.sub(TOKEN_MASCARA, texto)
    return limpar_texto_sensivel(texto)


def anonimizar_para_conhecimento(texto: str, nomes: Iterable[str] = ()) -> str:
    """Além da máscara: tira e-mail, telefone e nomes de pessoas conhecidas (clientes e
    funcionários), para a base de conhecimento da empresa nunca guardar dado pessoal."""
    texto = mascarar_pii(texto)
    texto = _EMAIL.sub("[e-mail]", texto)
    texto = _TELEFONE.sub("[telefone]", texto)
    for nome in sorted(
        {n.strip() for n in nomes if n and len(n.strip()) >= 3}, key=len, reverse=True
    ):
        texto = re.sub(re.escape(nome), "[cliente]", texto, flags=re.IGNORECASE)
    return texto
