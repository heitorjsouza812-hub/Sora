"""Relatar problema: máscara do diagnóstico, limites do esquema e o CLI do time.

O caminho com PostgreSQL (gravar, listar e retirar só os próprios) está em
``tests/integracao/test_contas.py``.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app import cli
from app.api.relatos import RelatoEntrada, mascarar_diagnostico, resumo_do_texto


def _diagnostico(**campos: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "versao_app": "0.1.0",
        "plataforma": "desktop",
        "rota": "/bots/123",
        "navegador": "Mozilla/5.0",
        "tela": "1440x900",
        "idioma": "pt-BR",
        "erros": [],
    }
    return {**base, **campos}


def test_mascara_email_cpf_cartao_e_token_no_diagnostico() -> None:
    bruto = _diagnostico(
        erros=[
            {
                "quando": "2026-11-20T10:00:00Z",
                "origem": "api",
                "mensagem": (
                    "falhou para ana.souza@empresa.com.br com CPF 529.982.247-25, "
                    "cartão 4111 1111 1111 1111 e Bearer eyJabc.def.ghi"
                ),
            }
        ]
    )
    mascarado = mascarar_diagnostico(bruto)
    mensagem = mascarado["erros"][0]["mensagem"]
    assert "ana.souza@empresa.com.br" not in mensagem
    assert "[e-mail]" in mensagem
    assert "529.982.247-25" not in mensagem
    assert "4111 1111 1111 1111" not in mensagem
    assert "eyJabc.def.ghi" not in mensagem
    assert mascarado["versao_app"] == "0.1.0"  # o resto continua legível


def test_esquema_limita_tamanhos_e_plataforma() -> None:
    RelatoEntrada(texto="O bot travou.", diagnostico=_diagnostico())
    with pytest.raises(ValidationError):
        RelatoEntrada(texto="")
    with pytest.raises(ValidationError):
        RelatoEntrada(texto="x" * 4_001)
    with pytest.raises(ValidationError):
        RelatoEntrada(texto="x", diagnostico=_diagnostico(plataforma="tv"))
    erro = {"quando": "2026-11-20T10:00:00Z", "origem": "app", "mensagem": "x"}
    with pytest.raises(ValidationError):
        RelatoEntrada(texto="x", diagnostico=_diagnostico(erros=[erro] * 21))


def test_resumo_numa_linha_com_reticencias() -> None:
    assert resumo_do_texto("linha 1\n\nlinha 2") == "linha 1 linha 2"
    longo = resumo_do_texto("a" * 300)
    assert len(longo) == 120
    assert longo.endswith("…")


def test_cli_relatos_listar_e_formatar() -> None:
    argumentos = cli.construir_parser().parse_args(["relatos", "listar", "--dias", "3"])
    assert (argumentos.recurso, argumentos.acao, argumentos.dias, argumentos.limite) == (
        "relatos",
        "listar",
        3,
        50,
    )
    assert cli.formatar_relatos([]) == "Nenhum relato no período."
    texto = cli.formatar_relatos(
        [
            {
                "id": "r1",
                "criado_em": "2026-11-20T10:00:00+00:00",
                "email": "ana@x.com",
                "texto": "O bot travou.",
                "diagnostico": {"plataforma": "web"},
            }
        ]
    )
    assert "ana@x.com · r1" in texto
    assert '"plataforma": "web"' in texto
