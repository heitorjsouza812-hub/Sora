"""Habilidades: receitas reutilizáveis no formato SKILL.md (o mesmo das Agent Skills da
Anthropic), compartilhadas entre os agentes do usuário. Tabela ``habilidades`` (migração 0004).

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``core/src/agent-skill.ts``
(``parseSkillMd``, ``buildSkillMd``, ``formatSkillsCatalogInstruction``,
``extractForcedSkillName``, ``extractRoutineSkillMentions``), ``core/src/teach-playbook.ts``
(o formato de playbook) e ``adapters/src/skill-tools.ts``.

- O usuário força uma habilidade com ``/Nome`` no começo da mensagem.
- Uma rotina carrega habilidades citadas como ``@Nome`` na hora de rodar.
- Habilidade é um passo a passo genérico; contas, canais e caixas de e-mail ficam no
  agendamento, não na habilidade.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.ferramentas.base import ErroFerramenta

MAX_NOME = 80
MAX_DESCRICAO = 2_000
MAX_CONTEUDO = 40_000
MAX_NO_CATALOGO = 50
_CERCA = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_FORCADA = re.compile(
    r"^(?:/|use\s+a\s+habilidade:\s*|use\s+skill:\s*)(.+?)(?:\n|$)", re.IGNORECASE
)
_PARADAS = {
    "e",
    "ou",
    "para",
    "com",
    "de",
    "do",
    "da",
    "via",
    "antes",
    "depois",
    "por",
    "o",
    "a",
    "then",
    "and",
    "or",
    "to",
    "for",
    "with",
    "the",
}
_MENCAO = re.compile(r"(?:^|[\s(,])@([A-Za-zÀ-ÿ][\w-]*(?:[ ]+[A-Za-zÀ-ÿ][\w-]*){0,5})(?=[\s,.)]|$)")


@dataclass(slots=True)
class SkillMd:
    nome: str
    descricao: str
    corpo: str
    frontmatter: dict[str, Any] = field(default_factory=dict)


def ler_skill_md(conteudo: str) -> SkillMd:
    """Lê um SKILL.md. Exige frontmatter YAML com ``name`` e ``description``.

    Chaves extras do frontmatter são preservadas (ida e volta sem perder nada).
    """
    texto = conteudo.lstrip("﻿")
    casamento = _CERCA.match(texto)
    if not casamento:
        raise ErroFerramenta("O SKILL.md precisa começar com frontmatter YAML (--- … ---).")
    try:
        frontmatter = yaml.safe_load(casamento.group(1)) or {}
    except yaml.YAMLError as erro:
        raise ErroFerramenta("Frontmatter do SKILL.md inválido.") from erro
    if not isinstance(frontmatter, dict):
        raise ErroFerramenta("O frontmatter do SKILL.md precisa ser um objeto.")
    nome = str(frontmatter.get("name") or "").strip()
    descricao = str(frontmatter.get("description") or "").strip()
    _validar(nome, descricao)
    corpo = texto[casamento.end() :].removeprefix("\n")
    return SkillMd(nome, descricao, corpo, frontmatter)


def _validar(nome: str, descricao: str) -> None:
    if not nome:
        raise ErroFerramenta("O SKILL.md precisa de 'name'.")
    if not descricao:
        raise ErroFerramenta("O SKILL.md precisa de 'description'.")
    if len(nome) > MAX_NOME:
        raise ErroFerramenta(f"O nome da habilidade passa de {MAX_NOME} caracteres.")
    if len(descricao) > MAX_DESCRICAO:
        raise ErroFerramenta(f"A descrição passa de {MAX_DESCRICAO} caracteres.")


def montar_skill_md(
    nome: str, descricao: str, corpo: str, frontmatter: dict[str, Any] | None = None
) -> str:
    """Monta o SKILL.md: ``name``, ``description`` e depois as outras chaves em ordem alfabética."""
    nome, descricao = nome.strip(), descricao.strip()
    _validar(nome, descricao)
    juntas = {**(frontmatter or {}), "name": nome, "description": descricao}
    ordem = sorted(juntas, key=lambda k: ({"name": 0, "description": 1}.get(k, 2), k))
    cabecalho = yaml.safe_dump(
        {k: juntas[k] for k in ordem}, allow_unicode=True, sort_keys=False, width=1_000
    ).rstrip("\n")
    corpo = corpo.removeprefix("\n")
    conteudo = f"---\n{cabecalho}\n---\n\n{corpo}"
    if len(conteudo) > MAX_CONTEUDO:
        raise ErroFerramenta(f"A habilidade passa de {MAX_CONTEUDO} caracteres.")
    return conteudo


class Playbook(BaseModel):
    """Formato de playbook ensinado (o usuário mostra a tarefa e ela vira habilidade)."""

    quando_usar: str = Field(min_length=1, max_length=500)
    entradas: list[str] = Field(default_factory=list, max_length=20)
    passos: list[str] = Field(min_length=1, max_length=60)
    como_conferir: str = Field(min_length=1, max_length=500)
    o_que_devolver: str = Field(min_length=1, max_length=500)
    limites_de_aprovacao: str = (
        "Não envie mensagens, não gaste dinheiro, não publique e não apague nada sem a "
        "aprovação explícita do usuário."
    )
    em_caso_de_falha: str = (
        "Se um passo falhar ou o resultado esperado não aparecer, pare e pergunte ao usuário "
        "antes de tentar de novo."
    )


def playbook_para_markdown(playbook: Playbook) -> str:
    linhas = [f"**Quando usar:** {playbook.quando_usar}"]
    if playbook.entradas:
        linhas.append(f"**Entradas:** {'; '.join(playbook.entradas)}")
    linhas.append("**Passos:**")
    linhas.extend(f"{i}. {passo}" for i, passo in enumerate(playbook.passos, 1))
    linhas += [
        f"**Como conferir:** {playbook.como_conferir}",
        f"**O que devolver:** {playbook.o_que_devolver}",
        f"**Limites de aprovação:** {playbook.limites_de_aprovacao}",
        f"**Se falhar:** {playbook.em_caso_de_falha}",
    ]
    return "\n".join(linhas) + "\n"


# ---------- ferramentas ----------


class LerHabilidade(BaseModel):
    """Lê o passo a passo de uma habilidade pelo nome."""

    nome: str = Field(min_length=1, max_length=MAX_NOME)


class CriarHabilidade(BaseModel):
    """Cria uma habilidade reutilizável (SKILL.md genérico)."""

    nome: str = Field(min_length=1, max_length=MAX_NOME)
    descricao: str = Field(min_length=1, max_length=MAX_DESCRICAO, description="Quando usar.")
    corpo: str = Field(
        min_length=1, max_length=MAX_CONTEUDO, description="Passo a passo em Markdown."
    )


class AtualizarHabilidade(BaseModel):
    """Atualiza uma habilidade criada pelo usuário."""

    nome: str = Field(min_length=1, max_length=MAX_NOME)
    descricao: str | None = Field(default=None, max_length=MAX_DESCRICAO)
    corpo: str | None = Field(default=None, max_length=MAX_CONTEUDO)


class ApagarHabilidade(BaseModel):
    """Apaga uma habilidade criada pelo usuário (pede aprovação)."""

    nome: str = Field(min_length=1, max_length=MAX_NOME)


# ---------- prompt ----------


def instrucao_de_habilidades(habilidades: list[tuple[str, str]]) -> str | None:
    """Catálogo ``(nome, descrição)`` para o prompt de sistema (até 50)."""
    if not habilidades:
        return None
    linhas = "\n".join(
        f"- {nome}: {descricao}" for nome, descricao in habilidades[:MAX_NO_CATALOGO]
    )
    return "\n".join(
        [
            "Habilidades disponíveis (receitas SKILL.md reutilizáveis, genéricas):",
            linhas,
            "Quando uma habilidade combinar com o pedido, chame ler_habilidade com o nome e siga "
            "o passo a passo. Prefira a habilidade a improvisar uma receita de vários passos.",
            "O usuário pode forçar uma habilidade com /Nome. Rotinas citam habilidades como @Nome.",
        ]
    )


def habilidade_forcada(pedido: str) -> tuple[str, str] | None:
    """``/Nome resto`` ou ``Use a habilidade: Nome`` no começo → ``(nome, resto)``."""
    texto = pedido.lstrip()
    casamento = _FORCADA.match(texto)
    if not casamento:
        return None
    nome = casamento.group(1).strip().lstrip("/").strip()
    if not nome or len(nome) > MAX_NOME:
        return None
    return nome, texto[casamento.end() :].lstrip()


def mencoes_em_rotina(pedido: str, conhecidas: list[str] | None = None) -> list[str]:
    """Habilidades citadas como ``@Nome`` num pedido de rotina, em ordem e sem repetir."""
    achadas: list[str] = []
    vistos: set[str] = set()
    if conhecidas:
        for nome in sorted((n.strip() for n in conhecidas if n.strip()), key=len, reverse=True):
            padrao = re.compile(rf"(?:^|[\s(,])@{re.escape(nome)}(?=[\s,.)]|$)", re.IGNORECASE)
            if padrao.search(pedido) and nome.lower() not in vistos:
                vistos.add(nome.lower())
                achadas.append(nome)
        return achadas
    for casamento in _MENCAO.finditer(pedido):
        partes = casamento.group(1).split()
        while len(partes) > 1 and partes[-1].lower() in _PARADAS:
            partes.pop()
        nome = " ".join(partes)
        if nome and nome.lower() not in {"todos", "everyone"} and nome.lower() not in vistos:
            vistos.add(nome.lower())
            achadas.append(nome)
    return achadas
