"""Política de aprovação por ferramenta: o que roda direto, o que pede cartão fixo e o que
passa pelo revisor de ações.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``core/src/action-approval.ts``
(``APPROVAL_EXEMPT_TOOLS``, ``APPROVAL_REQUIRED_BUILTIN_TOOLS``,
``EXPLICIT_APPROVAL_BUILTIN_TOOLS``, ``UNATTENDED_SAFE_BUILTIN_TOOLS`` e
``READ_ONLY_CONNECTOR_PATTERN``).

Princípio: na dúvida, pergunta. Ferramenta que não está em nenhuma lista e não parece só
leitura vai para o revisor; rotina rodando sem o usuário só usa as ferramentas seguras.
"""

from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import urlsplit

from publicsuffixlist import PublicSuffixList

_PSL = PublicSuffixList()
"""Lista pública de sufixos empacotada (offline, versão fixada no ``uv.lock``)."""


class Politica(StrEnum):
    LIVRE = "livre"
    """Roda sem perguntar: leitura, conversa e trabalho dentro da própria cadeia."""
    CARTAO_FIXO = "cartao_fixo"
    """Sempre pede aprovação ao usuário, sem modelo revisor (criar agente, mudar instruções…)."""
    REVISOR = "revisor"
    """Passa pelo revisor de ações antes (efeito fora da Sora)."""


LIVRES: frozenset[str] = frozenset(
    {
        # fase 1 (especificação §4)
        "falar",
        "perguntar",
        "disparar_especialista",
        "ver_especialista",
        "mensagem_especialista",
        "parar_especialista",
        "buscar_web",
        "ler_pagina",
        "ler_anexo",
        "escrever_arquivo",
        "gerar_imagem",
        "entregar",
        "veredito",
        # fase 2
        "buscar_memoria",
        "lembrar",
        "enviar_para_agente",
        "buscar_historico",
        "ler_historico",
        "catalogo_tarefas",
        "agendar",
        "listar_agendamentos",
        "cancelar_agendamento",
        "adicionar_pendencia",
        "listar_pendencias",
        "atualizar_pendencia",
        "concluir_pendencia",
        "remover_pendencia",
        "ler_habilidade",
        "criar_habilidade",
        "atualizar_habilidade",
        "gerar_grafico",
        # fase 3: navegar e ler não enviam nada
        "navegador_abrir",
        "navegador_ler",
        # navegador persistente, reações e canais de equipe (docs/referencias/openbot.md):
        # tudo fica dentro da Sora; a aba só é lida ou fechada, e o usuário vê o canal
        "navegador_abas",
        "navegador_fechar_aba",
        "navegador_capturar",
        "navegador_console",
        "navegador_pedir_ajuda",
        # navegador por árvore (docs/referencias/agent-desktop.md): ler, procurar e esperar não
        # mudam a página; navegador_acao, navegador_tecla e navegador_lote vão para o revisor
        "navegador_observar",
        "navegador_procurar",
        "navegador_elemento",
        "navegador_esperar",
        "reagir",
        "canal_historico",
        "canal_delegar",
        "canal_transferir",
        "canal_resultado",
        # meta-ferramentas do catálogo: a execução decide pela ferramenta de verdade
        "conectores_buscar_ferramentas",
        "conectores_carregar_ferramenta",
    }
)

CARTAO_FIXO: frozenset[str] = frozenset(
    {
        "criar_agente",
        "propor_instrucoes",
        "esquecer_memoria",
        "apagar_habilidade",
        "adicionar_servidor_mcp",
    }
)

REVISADAS: frozenset[str] = frozenset(
    {"chamar_conector", "executar_comando", "navegador_agir", "conectores_executar_ferramenta"}
)

SEGURAS_SEM_SUPERVISAO: frozenset[str] = frozenset(
    {
        "buscar_web",
        "ler_pagina",
        "ler_anexo",
        "buscar_memoria",
        "buscar_historico",
        "ler_historico",
        "catalogo_tarefas",
        "listar_agendamentos",
        "listar_pendencias",
        "ler_habilidade",
        "ver_especialista",
        "navegador_abrir",
        "navegador_ler",
        "navegador_abas",
        "navegador_console",
        "navegador_observar",
        "navegador_procurar",
        "navegador_elemento",
        "navegador_esperar",
        "canal_historico",
        "gerar_grafico",
        "conectores_buscar_ferramentas",
        "conectores_carregar_ferramenta",
    }
)
"""O que uma rotina agendada pode usar quando ninguém está olhando. O resto pausa."""

_SOMENTE_LEITURA = re.compile(
    r"(^|[_\-.])(get|list|search|find|read|fetch|query|view|"
    r"buscar|listar|ler|obter|consultar|ver|pesquisar|procurar)([_\-.]|$)",
    re.IGNORECASE,
)
_ESCRITA = re.compile(
    r"(^|[_\-.])(create|update|delete|remove|send|post|put|patch|write|set|add|move|archive|"
    r"publish|invite|share|pay|transfer|criar|atualizar|apagar|remover|enviar|publicar|"
    r"escrever|mover|pagar|compartilhar)([_\-.]|$)",
    re.IGNORECASE,
)


def parece_somente_leitura(nome: str) -> bool:
    """Heurística pelo nome: ``list_pages``, ``buscar_contatos`` → sim; ``send_and_list`` → não.

    Qualquer verbo de escrita no nome derruba a dica de leitura.
    """
    return bool(_SOMENTE_LEITURA.search(nome)) and not _ESCRITA.search(nome)


def _host(url: str) -> str:
    """Host em minúsculas e punycode; aceita endereço sem esquema (``evil.com/x``)."""
    texto = url.strip()
    if not texto:
        return ""
    if "://" not in texto:
        texto = "//" + texto.lstrip("/")
    try:
        host = (urlsplit(texto).hostname or "").rstrip(".").lower()
    except ValueError:
        return ""
    if not host:
        return ""
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""


def normalizar_dominio(valor: str) -> str:
    """Forma canônica para guardar e comparar aprovações (domínio registrável em punycode)."""
    return dominio_registravel(valor)


def dominio_registravel(url: str) -> str:
    """Domínio usado para a aprovação contextual do navegador.

    Usa a lista pública de sufixos (inclui hospedagens como ``github.io``, onde cada cliente é
    um domínio). IP e nome sem ponto ficam inteiros. Devolve ``""`` se não houver host: quem
    chama deve tratar isso como "pedir revisão".
    """
    host = _host(url)
    if not host:
        return ""
    if ":" in host or "." not in host or host.replace(".", "").isdigit():
        return host
    return _PSL.privatesuffix(host) or host


def navegacao_exige_revisao(
    url: str, *, perfil_tem_login: bool, dominios_aprovados: set[str] | frozenset[str]
) -> bool:
    """Regra única do A1: perfil com login + domínio não aprovado. Falha fechada.

    Domínio vazio (URL ilegível) num perfil logado também pede revisão.
    """
    if not perfil_tem_login:
        return False
    dominio = dominio_registravel(url)
    aprovados = {normalizar_dominio(d) for d in dominios_aprovados}
    return not dominio or dominio not in aprovados


def politica_contextual_navegador(
    nome: str,
    *,
    url: str,
    perfil_tem_login: bool,
    dominios_aprovados: set[str] | frozenset[str],
) -> Politica:
    """Eleva navegação para domínio novo quando o perfil contém uma sessão salva.

    Vale para abertura direta e para navegações disparadas por ações ou lotes. Perfil sem login
    preserva a política nominal da ferramenta.
    """
    base = politica_da_ferramenta(nome)
    if nome not in {"navegador_abrir", "navegador_agir", "navegador_acao", "navegador_lote"}:
        return base
    if navegacao_exige_revisao(
        url, perfil_tem_login=perfil_tem_login, dominios_aprovados=dominios_aprovados
    ):
        return Politica.REVISOR
    return base


def politica_da_ferramenta(nome: str, *, somente_leitura: bool | None = None) -> Politica:
    """Decide a política de uma ferramenta pelo nome.

    ``somente_leitura`` vem da anotação do MCP (``readOnlyHint``), quando houver; sem ela,
    vale a heurística do nome. Ferramenta desconhecida que não é só leitura → revisor.
    """
    if nome in CARTAO_FIXO:
        return Politica.CARTAO_FIXO
    if nome in REVISADAS or (nome.startswith("navegador_") and nome not in LIVRES):
        return Politica.REVISOR
    if nome in LIVRES:
        return Politica.LIVRE
    leitura = (
        parece_somente_leitura(nome.split("__")[-1]) if somente_leitura is None else somente_leitura
    )
    return Politica.LIVRE if leitura else Politica.REVISOR


def pode_sem_supervisao(nome: str, *, somente_leitura: bool | None = None) -> bool:
    """A ferramenta pode rodar numa rotina sem o usuário presente."""
    if nome in SEGURAS_SEM_SUPERVISAO:
        return True
    if nome.startswith("mcp__"):
        return politica_da_ferramenta(nome, somente_leitura=somente_leitura) is Politica.LIVRE
    return False
