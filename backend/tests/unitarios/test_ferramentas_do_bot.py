"""Achados do teste ao vivo (Faro-3, 2026-11-18): o que o bot e a Sora recebem de fato."""

from uuid import uuid4

from app.agentes.ferramentas_do_turno import nomes_diretos
from app.agentes.montagem import ContextoAgente, nomes_das_ferramentas
from app.ferramentas.permissoes import ferramentas_do_bot


def _contexto(papel: str, ferramentas_do_bot: list[str] | None) -> ContextoAgente:
    return ContextoAgente(
        usuario_id=uuid4(),
        agente_id=uuid4(),
        conversa_id=uuid4(),
        papel=papel,
        ferramentas_do_bot=ferramentas_do_bot,
    )


def test_bot_sem_buscar_web_nao_pesquisa() -> None:
    c = _contexto("individual", ["falar", "perguntar", "escrever_arquivo"])
    nomes = nomes_das_ferramentas(c)
    assert "buscar_web" not in nomes and "ler_pagina" not in nomes
    assert "escrever_arquivo" in nomes_diretos(nomes, c)


def test_bot_antigo_sem_lista_continua_com_o_padrao() -> None:
    assert "buscar_web" in ferramentas_do_bot([])
    assert "buscar_web" in ferramentas_do_bot(None)


def test_lista_do_bot_sempre_tem_falar_e_perguntar_e_as_implicitas() -> None:
    nomes = ferramentas_do_bot(["computador_agir"])
    assert {"falar", "perguntar", "computador_agir", "computador_abrir_programa"} <= set(nomes)


def test_bot_com_computador_tem_folga_de_passos() -> None:
    from app.agentes.middleware.limites import LIMITE_COM_NAVEGADOR, limites_do_agente

    c = _contexto("individual", ["falar", "computador_observar", "computador_agir"])
    assert limites_do_agente(c)[0] == LIMITE_COM_NAVEGADOR[0]


def test_sora_e_bot_tem_agenda_direto_e_sora_pesquisa() -> None:
    for papel, lista in (("sora", None), ("individual", ["falar"])):
        c = _contexto(papel, lista)
        diretos = set(nomes_diretos(nomes_das_ferramentas(c), c))
        assert {"agendar", "listar_agendamentos", "cancelar_agendamento"} <= diretos, papel
    sora = _contexto("sora", None)
    assert {"buscar_web", "ler_pagina"} <= set(nomes_diretos(nomes_das_ferramentas(sora), sora))


def test_regra_do_catalogo_de_conectores_so_quando_ele_existe() -> None:
    """Com até 20 ferramentas de conector elas vão direto e ``conectores_*`` não existe: o prompt
    não pode mandar o modelo chamar uma ferramenta que não está na lista (CI de 2026-11-19)."""
    from app.agentes.montagem import (
        REGRA_CATALOGO_CONECTORES,
        com_regra_do_catalogo,
        montar_prompt_de_sistema,
    )

    base = montar_prompt_de_sistema(_contexto("sora", None))
    assert "conectores_buscar_ferramentas" not in base
    direto = {"falar", "mcp__clima__buscar_clima"}
    assert com_regra_do_catalogo(base, direto) == base
    com_catalogo = com_regra_do_catalogo(base, direto | {"conectores_buscar_ferramentas"})
    assert com_catalogo.endswith(REGRA_CATALOGO_CONECTORES)
    assert "conectar_buscar_ferramentas" in com_catalogo  # o aviso do nome errado continua
