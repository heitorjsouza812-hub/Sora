"""Regress?es da montagem enxuta do Motor-2."""

import json
from uuid import uuid4

from langchain_core.utils.function_calling import convert_to_openai_tool

from app.agentes.ancora import catalogo_enxuto
from app.agentes.ferramentas_do_turno import nomes_diretos
from app.agentes.montagem import ContextoAgente, montar_prompt_de_sistema, nomes_das_ferramentas
from app.ferramentas.base import ContextoFerramenta
from app.ferramentas.catalogo_preguicoso import CatalogoFerramentas
from app.ferramentas.registro import criar_ferramentas


def test_bot_simples_tem_esquemas_enxutos_e_navegador_sob_demanda():
    c = ContextoAgente(
        usuario_id=uuid4(),
        agente_id=uuid4(),
        conversa_id=uuid4(),
        papel="individual",
        ferramentas_do_bot=[],
    )
    ferramentas = criar_ferramentas(
        nomes_das_ferramentas(c),
        ContextoFerramenta(
            usuario_id=c.usuario_id, agente_id=c.agente_id, conversa_id=c.conversa_id
        ),
    )
    diretos = set(nomes_diretos([f.name for f in ferramentas], c))
    escondidas = [f for f in ferramentas if f.name not in diretos]
    oferecidas = [f for f in ferramentas if f.name in diretos] + catalogo_enxuto(escondidas, [], c)
    esquemas = json.dumps([convert_to_openai_tool(f) for f in oferecidas], ensure_ascii=False)
    assert len(esquemas) < 6000
    assert "navegador_acao" not in diretos
    assert "navegador_acao" in {f.name for f in escondidas}
    assert len(montar_prompt_de_sistema(c)) < 6000


def test_catalogo_entrega_esquema_com_regras():
    c = ContextoAgente(
        usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4(), papel="individual"
    )
    ferramentas = criar_ferramentas(
        ["buscar_memoria"],
        ContextoFerramenta(
            usuario_id=c.usuario_id, agente_id=c.agente_id, conversa_id=c.conversa_id
        ),
    )
    catalogo = CatalogoFerramentas(ferramentas, guias={"buscar_memoria": "Confira a atualidade."})
    entrada = catalogo.carregar("buscar_memoria")
    assert entrada["esquema"]
    assert entrada["regras_de_uso"] == "Confira a atualidade."
