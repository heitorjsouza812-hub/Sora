"""Máscara de dados sensíveis dos canais da empresa.

Roda ANTES de gravar qualquer coisa que veio de um cliente (inclusive a mensagem crua) e de
novo sobre tudo que o modelo extrai. Mascara CPF, CNPJ, cartão de pagamento, CVV, senhas,
códigos de verificação e tokens/chaves, com qualquer mistura de espaços, pontos e hífens.

Decisão sobre telefone e e-mail (Prumo B5, 2026-11-15): **não** são mascarados na mensagem crua
nem na ficha. São o dado de contato que a ficha existe para guardar ("me chama no x@y.com"), o
telefone já é o identificador do contato no WhatsApp e o contato só some com "apagar cliente".
O que limita o dano é o prazo: a mensagem crua vence em ``retencao_dias`` (90) e os fatos em
``retencao_fatos_dias`` (365). Do conhecimento da empresa e das sugestões eles saem sempre
(``anonimizar_para_conhecimento``).
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

# Cadeia de grupos de dígitos ligados só por espaço, ponto, hífen ou barra ("529 982.247-25").
_CADEIA = re.compile(r"\d+(?:[ .\-/]{1,2}\d+){0,30}")
_GRUPO = re.compile(r"\d+")
_MAX_GRUPOS_POR_JANELA = 20
_MAX_DIGITOS = 19

_SEPARADOR_CVV = r"((?:\s*(?:[:=]|->|=>|é|eh|e|is|foi))*\s*)"
_CVV = re.compile(
    r"(?i)\b(cvv2?|cvc2?|cid|c[oó]d(?:igo)?\.?(?: de)? seguran[cç]a"
    r"|c[oó]d(?:igo)?\.? do cart[aã]o)\b" + _SEPARADOR_CVV + r"(\d{3,4})(?!\d)"
)
_CODIGO = re.compile(
    r"(?i)\b(c[oó]digo(?: de (?:verifica[cç][aã]o|acesso|confirma[cç][aã]o|seguran[cç]a))?|otp)\b"
    + _SEPARADOR_CVV
    + r"(\d{4,8})(?!\d)"
)
_CHAVE_DE_SENHA = re.compile(
    r"(?i)(?<![\w@\[-])(senhas?|password|passwd|pwd|pass|pin|puk|token|secret|segredo)(?![\w@\]-])"
)
_CHAVES_DE_TOKEN = frozenset({"token", "secret", "segredo"})
_PREENCHIMENTO = frozenset(
    "nova novo atual antiga antigo do da de dos das no na em para pra o a wifi wi-fi login conta "
    "banco email e-mail app cartao cartão internet roteador site".split()
)
_SEPARADORES = frozenset(
    {"é", "eh", "e", "is", "foi", "sera", "será", "seria", "ficou", "-", "\u2013"}
)
_PALAVRAS_COMUNS = frozenset(
    "que nao não foi ser sera será esta está para pra por com sem mas mais muito ja já ainda "
    "nova novo atual antiga antigo expirou expirada venceu vencida errada errado invalida inválida "
    "correta correto certa certo trocada trocado trocou resetada resetou salva salvo enviada "
    "enviado enviei mandei mando manda mandou veio chegou funciona funcionou deu deve devo "
    "preciso quero esqueci perdi lembro consigo consegui tem tenho temos fica vai vou "
    "pode posso podem aqui ali la lá se seu sua meu minha nosso nossa dela dele".split()
)
_TOKENS = (
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S
    ),
    re.compile(r"\bxox[abprso]-[A-Za-z0-9-]{10,}"),  # Slack
    re.compile(r"\bxapp-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bEAA[A-Za-z0-9]{20,}"),  # Meta / WhatsApp
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),  # AWS
    re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,}"),  # Stripe
    re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"),  # SendGrid
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{40,}\b"),
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TELEFONE = re.compile(r"(?<![\d.])(?:\+?55[ -]?)?\(?\d{2}\)?[ -]?9?\d{4}[ -]?\d{4}(?![\d-])")
_JA_MASCARADO = re.compile(r"^\[(?:CPF|CNPJ|cartão|senha|token|código|oculto|e-mail|telefone)\]")


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
    """Luhn em 13 a 19 dígitos. Telefone brasileiro com DDI (55 + 11 dígitos) não conta."""
    d = _digitos(texto)
    if not 13 <= len(d) <= 19 or len(set(d)) == 1:
        return False
    if d[0] == 5 and d[1] == 5 and len(d) == 13:
        return False
    soma = 0
    for i, digito in enumerate(reversed(d)):
        if i % 2:
            digito *= 2
            if digito > 9:
                digito -= 9
        soma += digito
    return soma % 10 == 0


def _classificar_janela(digitos: str) -> str | None:
    """Documento ou cartão que esses dígitos formam, se formam algum."""
    n = len(digitos)
    if n == 14 and cnpj_valido(digitos):
        return CNPJ_MASCARA
    if 13 <= n <= 19 and cartao_valido(digitos):
        return CARTAO_MASCARA
    if n == 11 and cpf_valido(digitos):
        return CPF_MASCARA
    return None


def _mascarar_numeros(texto: str) -> str:
    """CPF, CNPJ e cartão com qualquer mistura de espaços, pontos, hífens e barras, também
    quando vêm colados em outro número ("529 982 247 25 12345"): testa as janelas de grupos."""
    pedacos: list[str] = []
    cursor = 0
    for cadeia in _CADEIA.finditer(texto):
        base = cadeia.start()
        grupos = list(_GRUPO.finditer(cadeia.group()))
        com_mais = base > 0 and texto[base - 1] == "+"  # "+55 11 …" é telefone com DDI
        i = 0
        while i < len(grupos):
            achou: tuple[int, str] | None = None
            digitos = ""
            if not (i == 0 and com_mais):
                for j in range(i, min(len(grupos), i + _MAX_GRUPOS_POR_JANELA)):
                    digitos += grupos[j].group()
                    if len(digitos) > _MAX_DIGITOS:
                        break
                    rotulo = _classificar_janela(digitos)
                    if rotulo is not None:
                        achou = (j, rotulo)  # a janela mais longa que vale
            if achou is None:
                i += 1
                continue
            j, rotulo = achou
            pedacos.append(texto[cursor : base + grupos[i].start()])
            pedacos.append(rotulo)
            cursor = base + grupos[j].end()
            i = j + 1
    pedacos.append(texto[cursor:])
    return "".join(pedacos)


def _valor_de_segredo(texto: str, pos: int) -> tuple[int, int] | None:
    """Do ponto ``pos`` (logo depois da palavra-chave e do preenchimento), o trecho do valor:
    entre aspas (frase curta) ou a palavra até o espaço."""
    while pos < len(texto) and texto[pos] in " \t":
        pos += 1
    if pos >= len(texto):
        return None
    if texto[pos] in "\"'\u201c\u2018`":
        fecha = {"\u201c": "\u201d", "\u2018": "\u2019"}.get(texto[pos], texto[pos])
        ate = texto.find(fecha, pos + 1, pos + 62)
        if ate > pos + 1:
            return pos, ate + 1
    fim = pos
    while fim < len(texto) and not texto[fim].isspace():
        fim += 1
    while fim > pos + 1 and texto[fim - 1] in ".,;!?)" and texto[fim - 2].isalnum():
        fim -= 1
    return (pos, fim) if fim > pos else None


def _mascarar_senhas(texto: str) -> str:
    """ "senha Abc@123", "minha senha nova: hunter2", "a senha do wifi é X", "pin: 1234",
    "token xoxb-…": mascara o valor depois da palavra-chave (e do que vem no meio)."""
    saida: list[str] = []
    cursor = 0
    for achado in _CHAVE_DE_SENHA.finditer(texto):
        if achado.start() < cursor:
            continue
        chave = achado.group(1).lower()
        pos = achado.end()
        com_separador = False
        if pos < len(texto) and texto[pos] in ":=":
            com_separador = True
            pos += 1
        for _ in range(8):  # preenchimento e separador: "nova do wifi é:"
            m = re.match(r"\s*(\S+)", texto[pos:])
            if not m:
                break
            palavra = m.group(1).lower()
            termina_em_sinal = palavra.endswith((":", "="))
            base = palavra.rstrip(":=")
            if base in _SEPARADORES or palavra in {"->", "=>", ":", "="}:
                com_separador = True
            elif base in _PREENCHIMENTO:
                com_separador = com_separador or termina_em_sinal
            else:
                break
            pos += m.end()
        valor = _valor_de_segredo(texto, pos)
        if valor is None:
            continue
        ini, fim = valor
        candidato = texto[ini:fim]
        if _JA_MASCARADO.match(candidato):
            continue
        simples = candidato.lower().strip(".,;!?\"'\u201c\u201d\u2018\u2019`")
        parece_senha = any(not c.isalpha() for c in simples)
        if not parece_senha:
            if simples in _PALAVRAS_COMUNS:
                continue  # "esqueci a senha e não consigo entrar"
            if not com_separador and simples == "colorido":
                continue  # "o token expirou"
        saida.append(texto[cursor:ini])
        saida.append(TOKEN_MASCARA if chave in _CHAVES_DE_TOKEN else SENHA_MASCARA)
        cursor = fim
    saida.append(texto[cursor:])
    return "".join(saida)


def mascarar_pii(texto: str) -> str:
    """Mascara CPF, CNPJ, cartão, CVV, senha, código de verificação e tokens/chaves. Idempotente.

    E-mail e telefone **não** são mascarados aqui (veja o módulo): saem só do conhecimento."""
    if not texto:
        return texto
    texto = _mascarar_senhas(texto)
    texto = _CVV.sub(lambda m: f"{m.group(1)}{m.group(2)}{CODIGO_MASCARA}", texto)
    texto = _mascarar_numeros(texto)
    texto = _CODIGO.sub(lambda m: f"{m.group(1)}{m.group(2)}{CODIGO_MASCARA}", texto)
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
