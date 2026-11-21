"""Ensinar uma tarefa (Onda 3, item 14): as regras puras de ``app/navegador/ensinar.py``."""

from __future__ import annotations

import pytest

from app.navegador import ensinar as en


def test_descreve_o_elemento_pelo_papel_e_nome() -> None:
    assert en.descrever_alvo({"tag": "button", "nome": "Entrar"}) == "botão “Entrar”"
    assert en.descrever_alvo({"tag": "a", "nome": " Preços  e planos "}) == "link “Preços e planos”"
    assert en.descrever_alvo({"tag": "input", "tipo": "checkbox", "nome": "Lembrar"}) == (
        "caixa de marcar “Lembrar”"
    )
    assert en.descrever_alvo({"tag": "input", "tipo": "submit", "nome": "Ok"}) == "botão “Ok”"
    assert en.descrever_alvo({"tag": "div", "papel": "tab", "nome": ""}) == "aba"
    assert en.descrever_alvo(None) == "um ponto da página"
    longo = en.descrever_alvo({"tag": "button", "nome": "x" * 200})
    assert len(longo) < 80 and longo.endswith("…”")
    # aspas da página não quebram a frase
    assert en.descrever_alvo({"tag": "button", "nome": '"Ignore" tudo'}) == "botão “Ignore tudo”"


def test_texto_digitado_nunca_leva_senha_nem_dado_pessoal() -> None:
    assert en.texto_seguro("hunter2", senha=True) == "[senha]"
    assert en.texto_seguro("123.456.789-09", senha=False) == "[dado pessoal]"
    assert en.texto_seguro("minha senha é x", senha=False) == "[dado pessoal]"
    assert en.texto_seguro("notebook   dell", senha=False) == "notebook dell"
    assert en.texto_seguro("café com leite " * 10, senha=False).endswith("…")
    assert en.texto_seguro("a" * 100, senha=False) == "[dado pessoal]"  # parece token


def test_junta_digitacao_e_pagina_repetida() -> None:
    passos = [
        en.Passo(tipo="abrir", url="https://loja.exemplo/"),
        en.Passo(tipo="pagina", url="https://loja.exemplo/"),
        en.Passo(tipo="digitar", alvo="campo “Buscar”", texto="note"),
        en.Passo(tipo="digitar", alvo="campo “Buscar”", texto="book"),
        en.Passo(tipo="digitar", alvo="campo “Senha”", texto="[senha]"),
        en.Passo(tipo="digitar", alvo="campo “Senha”", texto="[senha]"),
    ]
    juntos = en.juntar_passos(passos)
    assert [p.tipo for p in juntos] == ["abrir", "digitar", "digitar", "digitar"]
    assert juntos[1].texto == "notebook"


def test_rascunho_vira_playbook_e_exige_passos() -> None:
    passos = [
        en.Passo(tipo="abrir", url="https://loja.exemplo/"),
        en.Passo(tipo="clicar", alvo="campo “Buscar”"),
        en.Passo(tipo="digitar", alvo="campo “Buscar”", texto="notebook"),
        en.Passo(tipo="tecla", texto="Enter"),
        en.Passo(tipo="pagina", url="https://loja.exemplo/busca"),
    ]
    rascunho = en.rascunho(passos, "Buscar um produto na loja", "loja.exemplo")
    assert rascunho.passos == 5 and rascunho.nome == "Buscar um produto na loja"
    corpo = rascunho.corpo
    for trecho in (
        "**Quando usar:** Quando o usuário pedir: Buscar um produto na loja. Site: loja.exemplo.",
        "1. Abra https://loja.exemplo/",
        "2. Clique em campo “Buscar”",
        "3. Em campo “Buscar”, digite “notebook”",
        "4. Aperte Enter",
        "5. Confira que abriu https://loja.exemplo/busca",
        "**Limites de aprovação:**",
    ):
        assert trecho in corpo, trecho
    with pytest.raises(ValueError, match="Nenhum passo"):
        en.rascunho([en.Passo(tipo="abrir", url="https://x.exemplo/")], "x", None)
