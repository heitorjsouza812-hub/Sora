"""Carregamento dos prompts (especificação §8.4: prompts são arquivos em
``backend/prompts``, com versão no nome; texto em ``03-prompts.md``).

Os trechos entre chaves (``{perfil_do_agente}``) são preenchidos aqui em cada
chamada. Também monta a cerca ``<dado_externo>`` de conteúdo não confiável.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PASTA_PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
"""``backend/prompts``."""

_CHAVE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
"""Só ``{nome_em_minusculas}`` é trecho a preencher; JSON literal (``{ "dano": …}``) não casa."""

_TAG_DA_CERCA = re.compile(r"<(/?)(dado_externo)", re.IGNORECASE)

VERSOES: dict[str, int] = {
    "sora_base": 1,
    "sistema1": 1,
    "planejador": 1,
    "especialista_comum": 1,
    "especialista_pesquisador": 1,
    "especialista_redator": 1,
    "especialista_designer": 1,
    "perfil_agente": 1,
    "verificador": 1,
    "revisor_acoes": 1,
    "memoria_sintese": 1,
    "memoria_verificacao": 1,
    "lembrete_inicio_turno": 1,
    "lembrete_silencio": 1,
    "lembrete_entrega": 1,
    "cerca_dado_externo": 1,
    "aviso_dado_externo": 1,
    # Adaptados do Rakazo (docs/referencias/rakazo.md):
    "compactacao_historico": 1,
    "juiz_rapido": 1,
}
"""Versão em uso de cada prompt; o arquivo é ``{nome}.v{versao}.md``."""


def carregar_prompt(nome: str, versao: int | None = None) -> str:
    """Lê ``{nome}.v{versao}.md`` (padrão: a versão de ``VERSOES``)."""
    if versao is None:
        if nome not in VERSOES:
            raise KeyError(f"Prompt sem versão registrada: {nome!r}.")
        versao = VERSOES[nome]
    return _ler_arquivo(nome, versao)


@lru_cache(maxsize=64)
def _ler_arquivo(nome: str, versao: int) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", nome):
        raise KeyError(f"Nome de prompt inválido: {nome!r}.")
    caminho = PASTA_PROMPTS / f"{nome}.v{versao}.md"
    if not caminho.is_file():
        raise FileNotFoundError(f"Prompt não encontrado: {caminho.name}.")
    return caminho.read_text(encoding="utf-8").rstrip("\n")


def preencher(modelo: str, **valores: Any) -> str:
    """Preenche os trechos ``{chave}`` do prompt; chave faltando é erro.

    Uma passada só: o texto inserido nunca é relido, então um ``{x}`` vindo do usuário ou
    da web não vira trecho a preencher.
    """
    faltando = sorted({chave for chave in _CHAVE.findall(modelo) if chave not in valores})
    if faltando:
        raise KeyError(f"Faltam valores para o prompt: {', '.join(faltando)}.")
    return _CHAVE.sub(lambda casamento: str(valores[casamento.group(1)]), modelo)


def neutralizar_cerca(conteudo: str) -> str:
    """Troca ``<dado_externo``/``</dado_externo`` vindos de fora por ``&lt;…``."""
    return _TAG_DA_CERCA.sub(
        lambda casamento: f"&lt;{casamento.group(1)}{casamento.group(2)}", conteudo
    )


def cercar(conteudo: str, origem: str) -> str:
    """Põe o conteúdo dentro de ``<dado_externo origem="...">``, neutralizando
    qualquer ``<dado_externo`` ou ``</dado_externo`` que já venha nele."""
    origem_limpa = re.sub(r"[<>\"\r\n]", " ", origem).strip()
    return preencher(
        carregar_prompt("cerca_dado_externo"),
        origem=origem_limpa,
        conteudo=neutralizar_cerca(conteudo),
    )
