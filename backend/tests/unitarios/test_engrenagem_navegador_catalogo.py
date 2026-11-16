"""Engrenagem: bot 1:1 com navegador recebe as 4 ferramentas diretas e o resto no catálogo que
ele tem de verdade (``conectores_*``), e o prompt do navegador fala desse catálogo.

Antes, com o navegador ligado, as 13 ferramentas iam direto em toda chamada e o prompt mandava
usar ``navegador_executar_ferramenta``, que a Sora e o bot 1:1 não têm (o modelo chamava uma
ferramenta inexistente e gastava passos).
"""

from __future__ import annotations

from uuid import uuid4

from app.agentes.ancora import NAVEGADOR_DIRETO, catalogo_enxuto
from app.agentes.ferramentas_do_turno import nomes_diretos, prompt_do_navegador
from app.agentes.montagem import (
    FERRAMENTAS_NAVEGADOR,
    ContextoAgente,
    montar_prompt_de_sistema,
    nomes_das_ferramentas,
)
from app.ferramentas.base import ContextoFerramenta
from app.ferramentas.registro import criar_ferramentas


def _bot_com_navegador() -> ContextoAgente:
    return ContextoAgente(
        usuario_id=uuid4(),
        agente_id=uuid4(),
        conversa_id=uuid4(),
        papel="individual",
        ferramentas_do_bot=list(FERRAMENTAS_NAVEGADOR),
        ferramentas_extras=list(FERRAMENTAS_NAVEGADOR),
    )


def test_so_quatro_do_navegador_vao_direto_e_o_resto_vai_ao_catalogo() -> None:
    contexto = _bot_com_navegador()
    todos = nomes_das_ferramentas(contexto)
    diretas = nomes_diretos(todos, contexto)
    assert {n for n in diretas if n.startswith("navegador_")} == set(NAVEGADOR_DIRETO)
    ferramentas = criar_ferramentas(
        todos,
        ContextoFerramenta(
            usuario_id=contexto.usuario_id,
            agente_id=contexto.agente_id,
            conversa_id=contexto.conversa_id,
        ),
    )
    escondidas = [f for f in ferramentas if f.name not in set(diretas)]
    meta = {f.name: f for f in catalogo_enxuto(escondidas, [], contexto)}
    assert set(meta) == {
        "conectores_buscar_ferramentas",
        "conectores_carregar_ferramenta",
        "conectores_executar_ferramenta",
    }
    assert "navegador_esperar" in meta["conectores_buscar_ferramentas"].description


def test_prompt_do_navegador_aponta_para_o_catalogo_que_o_bot_tem() -> None:
    texto = prompt_do_navegador("individual")
    assert "conectores_executar_ferramenta" in texto
    assert "navegador_executar_ferramenta" not in texto
    assert "navegador_executar_ferramenta" in prompt_do_navegador("pesquisador")
    sistema = montar_prompt_de_sistema(_bot_com_navegador())
    secao = sistema[sistema.index("## Como usar o navegador") :]
    assert "navegador_executar_ferramenta" not in secao
