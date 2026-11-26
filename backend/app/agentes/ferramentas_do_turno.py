"""Quais ferramentas vão no pedido ao modelo e quais ficam atrás do catálogo (Motor, A4 do Prumo-3).

Decidido pelo produto, não pelo plano grátis da Groq, que só existe nos testes (Heitor,
2026-11-18). Regra para a Sora e para o bot de conversa 1:1:

- **vão direto**: as que o bot tem habilitadas (o que o app mostra no perfil dele), as de
  conversa do papel (memória, agenda, pendências, histórico, habilidades, colegas, clientes) e o
  essencial (falar, perguntar, propor instruções), além de até 20 ferramentas MCP permitidas;
- **ficam no catálogo** (três meta-ferramentas, ``conectores_*``): conectores MCP (podem ser
  centenas) quando passam desse limite e as ferramentas extras do navegador. O modelo vê os nomes
  por grupo, carrega o esquema de uma e a executa pelo id. A política e o revisor decidem pelo nome
  de verdade.

Os outros papéis (especialistas da cadeia, bot de grupo) já têm conjuntos pequenos e não mudam.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agentes.montagem import ContextoAgente

PAPEIS_ENXUTOS = frozenset({"sora", "individual"})

ESSENCIAIS = frozenset(
    {
        "falar",
        "perguntar",
        "lembrar",
        "buscar_memoria",
        "propor_instrucoes",
        # Agenda direto: no teste ao vivo o modelo não procurava no catálogo e o lembrete se
        # perdia. O tamanho não é decidido pelo plano grátis da Groq (só existe nos testes; Heitor,
        # 2026-11-18).
        "agendar",
        "listar_agendamentos",
        "cancelar_agendamento",
    }
)
"""Pequenas, de uso comum e com efeito na tela (chip "Guardei isto", cartão de instruções)."""

GRUPO_DO_NAVEGADOR = "navegador"


def superficie_do_pedido(texto: str) -> str | None:
    if re.search(r"\b(?:meu|meu próprio) (?:pc|computador)\b", texto, re.I):
        return "computador"
    if re.search(r"\b(?:navegador|campo de (?:busca|pesquisa)|barra de pesquisa)\b", texto, re.I):
        return "navegador"
    return None


GRUPOS_ESCONDIDOS: dict[str, str] = {
    "buscar_historico": "historico",
    "ler_historico": "historico",
    "catalogo_tarefas": "historico",
    "adicionar_pendencia": "pendencias",
    "listar_pendencias": "pendencias",
    "atualizar_pendencia": "pendencias",
    "concluir_pendencia": "pendencias",
    "remover_pendencia": "pendencias",
    "ler_habilidade": "habilidades",
    "criar_habilidade": "habilidades",
    "atualizar_habilidade": "habilidades",
    "apagar_habilidade": "habilidades",
    "esquecer_memoria": "memoria",
    "enviar_para_agente": "colegas",
    "consultar_cliente": "empresa",
    "consultar_conhecimento": "empresa",
}


def grupo_da_escondida(nome: str) -> str:
    if nome.startswith("navegador_"):
        return GRUPO_DO_NAVEGADOR
    return GRUPOS_ESCONDIDOS.get(nome, "outros")


def nomes_diretos(nomes: list[str], contexto: ContextoAgente) -> list[str]:
    """Dos ``nomes`` permitidos, os que vão direto no pedido ao modelo (ordem preservada)."""
    if contexto.papel not in PAPEIS_ENXUTOS:
        return list(nomes)
    from app.agentes.ancora import ferramentas_do_papel
    from app.ferramentas.permissoes import ferramentas_do_bot

    # Produto, não plano grátis (Heitor, 2026-11-18): as ferramentas de conversa (memória,
    # pendências, histórico, habilidades, colegas, clientes) vão direto; no teste ao vivo o modelo
    # não as procurava no catálogo. O catálogo fica para o que é grande de verdade: conectores e as
    # ferramentas extras do navegador.
    habilitadas = set(ESSENCIAIS) | set(ferramentas_do_papel(contexto.papel))
    if contexto.papel == "sora":
        from app.agentes.montagem import FERRAMENTAS_POR_PAPEL

        habilitadas.update(FERRAMENTAS_POR_PAPEL["sora"])
    else:
        habilitadas.update(ferramentas_do_bot(contexto.ferramentas_do_bot))
    habilitadas.update(contexto.ferramentas_extras)
    from app.agentes.ancora import NAVEGADOR_DIRETO

    superficie = contexto.superficie
    if superficie and any(n.startswith(superficie + "_") for n in habilitadas):
        # O catálogo recebe somente ferramentas já permitidas para este papel/bot.
        # Isso deixa espaço para a árvore da página no pedido e mantém as demais acessíveis.
        habilitadas = {
            n
            for n in habilitadas
            if n.startswith(("navegador_", "computador_")) or n in {"falar", "perguntar"}
        }
    # Do navegador só as quatro de sempre vão direto (é o que o prompt do navegador ensina); as
    # outras nove ficam no catálogo. Antes, com o navegador ligado, as 13 iam direto e o prompt
    # mandava usar um ``navegador_executar_ferramenta`` que este bot não tem.
    return [
        n
        for n in nomes
        if n in habilitadas and (not n.startswith("navegador_") or n in NAVEGADOR_DIRETO)
    ]


def nomes_escondidos(nomes: list[str], contexto: ContextoAgente) -> list[str]:
    diretos = set(nomes_diretos(nomes, contexto))
    return [n for n in nomes if n not in diretos]


def prompt_do_navegador(papel: str, *, catalogo_confirmado: bool = True) -> str:
    """Prompt do navegador com os nomes do catálogo que este papel tem de verdade.

    A Sora e o bot 1:1 têm um catálogo só (``conectores_*``); os outros papéis têm o catálogo
    próprio do navegador (``navegador_*_ferramenta(s)``), que é o que o arquivo do prompt descreve.
    """
    from app.agentes.prompts import carregar_prompt

    texto = carregar_prompt("navegador_arvore")
    if papel not in PAPEIS_ENXUTOS:
        return texto
    if catalogo_confirmado:
        for acao in ("buscar_ferramentas", "carregar_ferramenta", "executar_ferramenta"):
            texto = texto.replace(f"navegador_{acao}", f"conectores_{acao}")
        return texto
    # Os nomes do catálogo entram após montar as ferramentas reais do turno.
    return "\n".join(
        linha
        if "navegador_buscar_ferramentas" not in linha
        else "- Para as ações extras, use o catálogo disponível neste turno, no grupo navegador."
        for linha in texto.splitlines()
    )
