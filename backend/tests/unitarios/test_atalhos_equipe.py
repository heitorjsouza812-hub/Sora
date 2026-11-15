import pytest

from app.sistema1.atalhos_equipe import (
    NOME_PADRAO,
    PAPEL_PADRAO,
    intencao_de_equipe,
    nome_e_papel_do_bot,
)


@pytest.mark.parametrize(
    ("pedido", "esperado"),
    [
        ("Crie um bot chamado Resumo que resume textos.", "bot"),
        ("Quero criar um bot de atendimento.", "bot"),
        ("Crie um bot para mim.", "bot"),
        ("Use a sua ferramenta criar_agente para criar um bot.", "bot"),
        ("Preciso de uma equipe de bots para lançar minha cafeteria.", "grupo"),
        ("Monte um grupo com bots.", "grupo"),
        ("Quero uma equipe para lançar a campanha.", "grupo"),
        ("Peça ao bot Redator que revise este texto.", None),
        ("Envie este pedido ao grupo Marketing.", None),
        ("Quero ver o grupo Marketing.", None),
        ("Qual é a capital da França?", None),
        ("O que você consegue fazer?", None),
    ],
)
def test_intencao_de_equipe_com_frases_reais(pedido, esperado):
    assert intencao_de_equipe(pedido) == esperado


@pytest.mark.parametrize(
    ("pedido", "nome", "papel"),
    [
        ("Crie um bot chamado Resumo que resume textos.", "Resumo", "Resume textos"),
        ("Quero criar um bot de atendimento.", NOME_PADRAO, "Bot de atendimento"),
        ("Crie um bot para mim.", NOME_PADRAO, PAPEL_PADRAO),
        ("Use a sua ferramenta criar_agente para criar um bot.", NOME_PADRAO, PAPEL_PADRAO),
    ],
)
def test_nome_e_papel_provisorios_do_rascunho(pedido, nome, papel):
    assert nome_e_papel_do_bot(pedido) == (nome, papel)
