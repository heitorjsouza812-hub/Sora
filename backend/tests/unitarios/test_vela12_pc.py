"""Vela-12: o controle do PC (C3) fazendo de verdade uma tarefa simples (Excel).

Teste real (2026-11-15): "Café\\t2\\t10,50\\n" era recusado como senha (a linha inteira contava
como uma palavra só), então nenhuma tabela com preço passava.
"""

from __future__ import annotations

import pytest

from app.computador.interface import parece_senha


@pytest.mark.parametrize(
    "linha",
    [
        "Produto\tQuantidade\tPreço\n",
        "Café\t2\t10,50\n",
        "Pão de queijo\t6\t0,80\n",
        "Leite\t3\t5,20",
        "Total\t=B2*C2\n",
        "Ana Souza\tana@empresa.com.br\t(11) 91234-5678\n",
    ],
)
def test_linha_de_planilha_nao_e_senha(linha: str) -> None:
    assert not parece_senha(linha)


@pytest.mark.parametrize(
    "linha",
    [
        "login\tS3nh@Forte!\n",  # a célula com cara de senha continua recusada
        "Abc123!@#\tqualquer\n",
        "conta\tusuario\nXy7#kq9!Lm\n",
        "token\tsk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789\n",
    ],
)
def test_celula_com_cara_de_senha_continua_recusada(linha: str) -> None:
    assert parece_senha(linha)
