"""Regras instantâneas do Sistema 1 (antes de qualquer modelo).

Especificação: §7 "Como ligar no Sistema 1" passo 1 ("Regras: saudações, comandos fixos e
verbos de ação externa (enviar, pagar, publicar, apagar). Instantâneo.") e regra de segurança:
as regras só podem acrescentar risco, nunca tirar.

As regras erram para o lado do risco ("na dúvida, marque risco"): só reconhecem formas do verbo
em que a leitura de pedido é provável (infinitivo, imperativo, passado, gerúndio, particípio),
para não marcar substantivos comuns como "agenda", "formato" ou "página".
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from app.sistema1.esquemas import Risco

# Verbos que marcam ação externa/destrutiva (lista inicial da §7 mais os do prompt do Sistema 1;
# a equipe amplia com os dados de treino).
VERBOS_ACAO_EXTERNA: tuple[str, ...] = (
    "enviar",
    "mandar",
    "pagar",
    "publicar",
    "postar",
    "comprar",
    "agendar",
    "reservar",
    "contratar",
    "transferir",
)
VERBOS_DESTRUTIVOS: tuple[str, ...] = ("apagar", "excluir", "deletar", "destruir", "eliminar")

# Verbos regulares em -ar: (radical, radical antes de "e" no subjuntivo/imperativo).
_FINAIS_AR = ("ar", "ou", "ei", "amos", "aram", "ando", "ado", "ada", "ados", "adas")
_FINAIS_AR_COM_E = ("e", "es", "em", "emos")
_FINAIS_ER_IR = ("er", "ir", "eu", "iu", "i", "indo", "endo", "ido", "ida", "idos", "idas")
_FINAIS_UIR = ("ir", "i", "iu", "indo", "ido", "ida", "ia", "ua", "ui")

_RADICAIS: dict[str, tuple[str, str]] = {
    "enviar": ("envi", "envi"),
    "mandar": ("mand", "mand"),
    "pagar": ("pag", "pagu"),
    "publicar": ("public", "publiqu"),
    "postar": ("post", "post"),
    "comprar": ("compr", "compr"),
    "agendar": ("agend", "agend"),
    "reservar": ("reserv", "reserv"),
    "contratar": ("contrat", "contrat"),
    "apagar": ("apag", "apagu"),
    "deletar": ("delet", "delet"),
    "eliminar": ("elimin", "elimin"),
}


def _padrao_do_verbo(verbo: str) -> re.Pattern[str]:
    """Expressão que reconhece as formas de pedido do verbo (texto já sem acentos)."""
    if verbo == "transferir":
        formas = [f"transfer{f}" for f in _FINAIS_ER_IR] + ["transfira", "transfere"]
    elif verbo == "excluir":
        formas = [f"exclu{f}" for f in _FINAIS_UIR]
    elif verbo == "destruir":
        formas = [f"destru{f}" for f in _FINAIS_UIR] + ["destrua", "destroi"]
    else:
        radical, radical_e = _RADICAIS[verbo]
        formas = [f"{radical}{f}" for f in _FINAIS_AR]
        formas += [f"{radical_e}{f}" for f in _FINAIS_AR_COM_E]
    return re.compile(r"\b(?:" + "|".join(sorted(set(formas), key=len, reverse=True)) + r")\b")


_PADROES: dict[str, re.Pattern[str]] = {
    verbo: _padrao_do_verbo(verbo) for verbo in (*VERBOS_ACAO_EXTERNA, *VERBOS_DESTRUTIVOS)
}

_SAUDACAO = re.compile(
    r"^(?:oi|ola|opa|eai|e ai|hey|hello|hi|bom dia|boa tarde|boa noite|tudo bem|tudo bom|"
    r"obrigad[oa]|valeu|beleza|salve)\b"
)
_LIMITE_PALAVRAS_DA_SAUDACAO = 5
_COMANDO_FIXO = re.compile(r"^/([a-z0-9][a-z0-9_-]*)")

_ORDEM_DE_RISCO = {Risco.NENHUM: 0, Risco.ACAO_EXTERNA: 1, Risco.DESTRUTIVO: 2}


class ResultadoRegras(BaseModel):
    """O que as regras conseguiram decidir sozinhas. Campo ``None`` = deixa para o N1."""

    risco: Risco = Risco.NENHUM
    saudacao: bool = False
    comando_fixo: str | None = None  # ex.: "/skill", se houver comandos fixos
    verbos_encontrados: list[str] = Field(default_factory=list)


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e com espaços simples: base de todas as regras."""
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    sem_acentos = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acentos).strip()


def aplicar_regras(pedido: str) -> ResultadoRegras:
    """Roda as regras sobre o texto do pedido (sem rede, sem modelo)."""
    texto = normalizar(pedido)
    comando = _COMANDO_FIXO.match(texto)
    sem_pontuacao = re.sub(r"[^\w\s]", " ", texto)
    palavras = sem_pontuacao.split()
    saudacao = bool(
        _SAUDACAO.match(" ".join(palavras)) and len(palavras) <= _LIMITE_PALAVRAS_DA_SAUDACAO
    )

    encontrados = [verbo for verbo, padrao in _PADROES.items() if padrao.search(texto)]
    if any(verbo in VERBOS_DESTRUTIVOS for verbo in encontrados):
        risco = Risco.DESTRUTIVO
    elif encontrados:
        risco = Risco.ACAO_EXTERNA
    else:
        risco = Risco.NENHUM
    return ResultadoRegras(
        risco=risco,
        saudacao=saudacao,
        comando_fixo=f"/{comando.group(1)}" if comando else None,
        verbos_encontrados=encontrados,
    )


def juntar_risco(*riscos: Risco) -> Risco:
    """O maior risco vence (regras, Laya ou N1): ninguém tira risco, só acrescenta."""
    return max(riscos, key=_ORDEM_DE_RISCO.__getitem__, default=Risco.NENHUM)
