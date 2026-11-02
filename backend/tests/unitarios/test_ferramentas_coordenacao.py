"""Ferramentas de coordenação (Elo): registro, permissões, rótulos e esquemas. Sem banco."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.ferramentas.base import ContextoFerramenta
from app.ferramentas.perguntar import Opcao, Perguntar, id_da_pergunta
from app.ferramentas.permissoes import FERRAMENTAS_POR_PAPEL, ferramentas_do_agente
from app.ferramentas.registro import ESQUEMAS, FERRAMENTAS_QUE_ENCERRAM, criar_ferramentas
from app.ferramentas.rotulos import resumir_resultado


def _contexto() -> ContextoFerramenta:
    return ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4())


def test_ferramentas_do_agente_junta_papel_e_extras_sem_repetir() -> None:
    nomes = ferramentas_do_agente("redator", ["buscar_web", "entregar"])
    assert nomes == ["ler_anexo", "escrever_arquivo", "entregar", "buscar_web"]
    assert ferramentas_do_agente("papel_que_nao_existe") == []


def test_todo_papel_so_usa_ferramentas_registradas() -> None:
    for papel, nomes in FERRAMENTAS_POR_PAPEL.items():
        assert set(nomes) <= set(ESQUEMAS), papel


def test_criar_ferramentas_monta_tools_com_esquema_e_encerramento() -> None:
    ferramentas = criar_ferramentas(["entregar", "perguntar", "veredito", "entregar"], _contexto())
    assert [f.name for f in ferramentas] == ["entregar", "perguntar", "veredito"]
    for ferramenta in ferramentas:
        assert ferramenta.args_schema is ESQUEMAS[ferramenta.name]
        assert ferramenta.return_direct is (ferramenta.name in FERRAMENTAS_QUE_ENCERRAM)
        assert ferramenta.description


def test_criar_ferramentas_recusa_nome_desconhecido() -> None:
    with pytest.raises(ValueError, match="desconhecida"):
        criar_ferramentas(["nao_existe"], _contexto())


async def test_erro_de_ferramenta_volta_para_o_modelo_como_texto() -> None:
    ferramenta = criar_ferramentas(["disparar_especialista"], _contexto())[0]
    # sem cadeia na conversa a ferramenta recusa; o laço do agente continua
    resposta = await ferramenta.ainvoke({"papel": "redator", "tarefa": "escrever"})
    assert resposta.startswith("Erro:")


def test_id_da_pergunta_e_estavel_e_depende_do_contexto() -> None:
    contexto = _contexto()
    pergunta = Perguntar(
        texto="Qual tom?",
        opcoes=[Opcao(rotulo="Formal", valor="formal"), Opcao(rotulo="Leve", valor="leve")],
    )
    assert id_da_pergunta(pergunta, contexto) == id_da_pergunta(pergunta, contexto)
    assert id_da_pergunta(pergunta, contexto) != id_da_pergunta(pergunta, _contexto())


def test_resumir_resultado_links_e_itens() -> None:
    resultado = {
        "resultados": [
            {"titulo": "Café", "url": "https://www.exemplo.com.br/cafe"},
            {"titulo": "Outro", "url": "https://blog.org/x"},
        ]
    }
    resumo = resumir_resultado("buscar_web", resultado)
    assert resumo["links"] == [
        {"titulo": "Café", "dominio": "exemplo.com.br"},
        {"titulo": "Outro", "dominio": "blog.org"},
    ]
    assert resumir_resultado("x", ["a", "b"])["itens"] == ["a", "b"]
    assert resumir_resultado("x", None)["resumo"] == "Concluído"
