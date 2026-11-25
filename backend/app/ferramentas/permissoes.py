"""Ferramentas permitidas por papel (especificação §4, ``FERRAMENTAS_POR_PAPEL``).

O backend só entrega a um agente as ferramentas listadas aqui para o papel
dele ou em ``agentes.ferramentas`` (agente individual).
"""

FERRAMENTAS_NAVEGADOR = (
    "navegador_abrir",
    "navegador_abas",
    "navegador_fechar_aba",
    "navegador_capturar",
    "navegador_console",
    "navegador_pedir_ajuda",
    "navegador_observar",
    "navegador_procurar",
    "navegador_elemento",
    "navegador_esperar",
    "navegador_acao",
    "navegador_tecla",
    "navegador_lote",
)

FERRAMENTAS_POR_PAPEL: dict[str, list[str]] = {
    "sora": [
        "falar",
        "perguntar",
        "criar_agente",
        "propor_grupo",
        "disparar_especialista",
        "ver_especialista",
        "mensagem_especialista",
        "parar_especialista",
        "ler_anexo",
        # O prompt da Sora manda usar as duas em pedido simples, mas ela não as tinha e inventava
        # uma recusa (Faro-3, 2026-11-18).
        "buscar_web",
        "ler_pagina",
        *FERRAMENTAS_NAVEGADOR,
    ],
    "pesquisador": ["buscar_web", "ler_pagina", "ler_anexo", "entregar"],
    "redator": ["ler_anexo", "escrever_arquivo", "entregar"],
    "designer": ["ler_anexo", "gerar_imagem", "entregar"],
    "verificador": ["buscar_web", "ler_pagina", "ler_anexo", "veredito"],
    "individual": [
        "falar",
        "perguntar",
        "ler_anexo",
        "buscar_web",
        "ler_pagina",
        "escrever_arquivo",
    ],
}

FERRAMENTAS_COM_REVISOR: frozenset[str] = frozenset()
"""Ferramentas que passam pelo revisor de ações. Vazio na fase 1 (``criar_agente``
usa cartão fixo; ``chamar_conector`` e ``executar_comando`` entram na fase 3)."""

FERRAMENTAS_COM_CERCA: frozenset[str] = frozenset({"buscar_web", "ler_pagina", "ler_anexo"})
"""Resultados que entram na cerca ``<dado_externo>`` (§4; ``chamar_conector`` na fase 3)."""


IMPLICITAS: dict[str, tuple[str, ...]] = {
    "computador_agir": ("computador_abrir_programa",),
}
"""Ferramenta que vem junto de outra que o bot já tem (Vela-12): quem age no computador também
abre programa pelo nome (lista fechada; no PC do usuário passa pelo cartão do programa)."""


def ferramentas_do_bot(lista_do_bot: list[str] | None) -> list[str]:
    """Ferramentas de um bot 1:1: a lista dele (o que o app mostra) mais falar e perguntar.

    Antes a lista padrão do papel ``individual`` era sempre somada: tirar ``buscar_web`` do bot
    não adiantava e ele pesquisava mesmo assim (Faro-3, 2026-11-18). Bot sem lista gravada (os
    antigos, ``{}``) continua com o padrão.
    """
    if not lista_do_bot:
        return ferramentas_do_agente("individual")
    return ferramentas_do_agente("individual_minimo", ["falar", "perguntar", *lista_do_bot])


def ferramentas_do_agente(papel: str, extras: list[str] | None = None) -> list[str]:
    """Nomes das ferramentas que o agente pode usar (papel + ``agentes.ferramentas``)."""
    base = FERRAMENTAS_POR_PAPEL.get(papel, [])
    nomes: list[str] = []
    for nome in [*base, *(extras or [])]:
        for item in (nome, *IMPLICITAS.get(nome, ())):
            if item not in nomes:
                nomes.append(item)
    return nomes
