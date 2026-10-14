"""Ferramentas permitidas por papel (especificação §4, ``FERRAMENTAS_POR_PAPEL``).

O backend só entrega a um agente as ferramentas listadas aqui para o papel
dele ou em ``agentes.ferramentas`` (agente individual).
"""

FERRAMENTAS_POR_PAPEL: dict[str, list[str]] = {
    "sora": [
        "falar",
        "perguntar",
        "disparar_especialista",
        "ver_especialista",
        "mensagem_especialista",
        "parar_especialista",
        "ler_anexo",
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


def ferramentas_do_agente(papel: str, extras: list[str] | None = None) -> list[str]:
    """Nomes das ferramentas que o agente pode usar (papel + ``agentes.ferramentas``)."""
    raise NotImplementedError
