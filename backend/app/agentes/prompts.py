"""Carregamento dos prompts (especificação §8.4: prompts são arquivos em
``backend/prompts``, com versão no nome; texto em ``03-prompts.md``).

Os trechos entre chaves (``{perfil_do_agente}``) são preenchidos aqui em cada
chamada. Também monta a cerca ``<dado_externo>`` de conteúdo não confiável.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

PASTA_PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
"""``backend/prompts``."""

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
}
"""Versão em uso de cada prompt; o arquivo é ``{nome}.v{versao}.md``."""


def carregar_prompt(nome: str, versao: int | None = None) -> str:
    """Lê ``{nome}.v{versao}.md`` (padrão: a versão de ``VERSOES``)."""
    raise NotImplementedError


def preencher(modelo: str, **valores: Any) -> str:
    """Preenche os trechos ``{chave}`` do prompt; chave faltando é erro."""
    raise NotImplementedError


def cercar(conteudo: str, origem: str) -> str:
    """Põe o conteúdo dentro de ``<dado_externo origem="...">``, neutralizando
    qualquer ``<dado_externo`` ou ``</dado_externo`` que já venha nele."""
    raise NotImplementedError
