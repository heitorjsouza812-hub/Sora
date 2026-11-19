"""Quais ferramentas vão no pedido ao modelo e quais ficam atrás do catálogo (Motor, A4 do Prumo-3).

Cada ferramenta que vai direto custa o esquema inteiro em TODA chamada ao modelo. No plano
grátis da Groq (6 a 8 mil tokens por minuto) 32 ferramentas de um bot simples (17 mil caracteres)
não cabiam. Regra para a Sora e para o bot de conversa 1:1:

- **vão direto**: as que o bot tem habilitadas (o que o app mostra no perfil dele), mais o
  essencial de qualquer conversa: falar, perguntar, lembrar, buscar na memória e propor
  instruções (cartão);
- **ficam no catálogo** (três meta-ferramentas, ``conectores_*``): navegador, histórico,
  pendências, habilidades, enviar a colegas… O modelo vê os nomes por grupo, carrega o esquema de
  uma e a executa pelo id. A política e o revisor continuam decidindo pelo nome de verdade.

Os outros papéis (especialistas da cadeia, bot de grupo) já têm conjuntos pequenos e não mudam.
"""

from __future__ import annotations

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
    from app.ferramentas.permissoes import ferramentas_do_bot

    habilitadas = set(ESSENCIAIS)
    if contexto.papel == "sora":
        from app.agentes.montagem import FERRAMENTAS_POR_PAPEL

        habilitadas.update(FERRAMENTAS_POR_PAPEL["sora"])
    else:
        habilitadas.update(ferramentas_do_bot(contexto.ferramentas_do_bot))
    habilitadas.update(contexto.ferramentas_extras)
    from app.agentes.ancora import NAVEGADOR_DIRETO

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


def prompt_do_navegador(papel: str) -> str:
    """Prompt do navegador com os nomes do catálogo que este papel tem de verdade.

    A Sora e o bot 1:1 têm um catálogo só (``conectores_*``); os outros papéis têm o catálogo
    próprio do navegador (``navegador_*_ferramenta(s)``), que é o que o arquivo do prompt descreve.
    """
    from app.agentes.prompts import carregar_prompt

    texto = carregar_prompt("navegador_arvore")
    if papel not in PAPEIS_ENXUTOS:
        return texto
    for acao in ("buscar_ferramentas", "carregar_ferramenta", "executar_ferramenta"):
        texto = texto.replace(f"navegador_{acao}", f"conectores_{acao}")
    return texto.replace("catálogo do navegador", "catálogo `conectores` (grupo navegador)")
