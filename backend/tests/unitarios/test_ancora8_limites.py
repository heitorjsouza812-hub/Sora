"""Âncora-8 (A3 do Prumo-4): minuto, cota do dia e pedido grande demais têm cada um o seu
texto em todos os caminhos (triagem, conversa, cadeia, rotina); chave recusada e provedor fora
do ar também não viram "limite por minuto"."""

from __future__ import annotations

import litellm
import pytest

from app.api.conversas import MENSAGEM_FALHA_DO_PROVEDOR, _texto_da_falha_da_triagem
from app.llm.limite import (
    MENSAGEM_CHAVE_RECUSADA,
    MENSAGEM_PROVEDOR_FORA,
    ErroLimiteDoProvedor,
    mensagem_da_falha_do_provedor,
    mensagem_de_limite,
)
from app.sistema1.triagem import SemModeloDisponivel

COTA = (
    "Rate limit reached for model `openai/gpt-oss-120b` on tokens per day (TPD): Limit 200000, "
    "Used 199900, Requested 500. Please try again in 9m10.5s."
)
MINUTO = "Rate limit reached on tokens per minute (TPM): Limit 8000. Please try again in 26s."
GRANDE = "Request too large for model on tokens per minute (TPM): Limit 8000, Requested 12000."


def _limite(texto: str) -> Exception:
    return litellm.RateLimitError(texto, llm_provider="groq", model="m")


def _grande(texto: str) -> Exception:
    return litellm.APIError(413, texto, llm_provider="groq", model="m")


def _com_status(codigo: int, texto: str) -> Exception:
    erro = RuntimeError(texto)
    erro.status_code = codigo  # type: ignore[attr-defined]
    return erro


def test_os_tres_limites_cru_do_provedor_viram_tres_textos():
    minuto = mensagem_de_limite(_limite(MINUTO))
    dia = mensagem_de_limite(_limite(COTA))
    grande = mensagem_de_limite(_grande(GRANDE))
    assert minuto and dia and grande
    assert len({minuto, dia, grande}) == 3
    assert "por minuto" in minuto
    assert "cota diária" in dia and "outro modelo" in dia and "por minuto" not in dia
    assert "550 segundos" in dia or "551 segundos" in dia  # 9m10,5s do provedor
    assert "Compacte" in grande


def test_erro_do_motor_ja_montado_mantem_o_proprio_texto():
    for detalhe in ("limite por minuto", "pedido grande demais", "cota do dia: tente em 5 s"):
        erro = ErroLimiteDoProvedor(detalhe)
        assert mensagem_de_limite(RuntimeError("wrap")) is None
        try:
            raise RuntimeError("wrap") from erro
        except RuntimeError as embrulho:
            assert mensagem_de_limite(embrulho) == str(erro)


def test_cota_do_dia_nao_tem_o_prefixo_tecnico():
    texto = str(ErroLimiteDoProvedor("cota do dia: tente novamente em 198 segundos"))
    assert texto.startswith("A cota diária deste modelo acabou. Tente novamente em 198 segundos")
    assert "cota do dia:" not in texto


def test_erro_que_nao_e_de_limite_nao_vira_limite():
    assert mensagem_de_limite(ValueError("x")) is None
    assert mensagem_de_limite(litellm.AuthenticationError("ruim", "groq", "m")) is None


@pytest.mark.parametrize(
    ("erro", "esperado"),
    [
        (_limite(MINUTO), "por minuto"),
        (_limite(COTA), "cota diária"),
        (_grande(GRANDE), "Compacte"),
        (litellm.AuthenticationError("chave ruim", llm_provider="groq", model="m"), "chave"),
        (_com_status(403, "negado"), "chave"),
        (
            litellm.InternalServerError("caiu", llm_provider="groq", model="m"),
            "fora do ar",
        ),
        (
            litellm.ServiceUnavailableError("503", llm_provider="groq", model="m"),
            "fora do ar",
        ),
        (TimeoutError(), "fora do ar"),
    ],
)
def test_a_triagem_distingue_limite_cota_chave_e_provedor_fora(erro, esperado):
    texto = _texto_da_falha_da_triagem(erro)
    assert esperado in texto
    assert "Sua mensagem foi guardada" in texto
    if esperado != "por minuto":
        assert "por minuto" not in texto
    if esperado != "chave":
        assert "Veja a chave" not in texto


def test_a_triagem_cai_no_texto_geral_para_o_resto():
    for erro in (SemModeloDisponivel("nenhum"), ValueError("saída ilegível")):
        assert _texto_da_falha_da_triagem(erro) == MENSAGEM_FALHA_DO_PROVEDOR


def test_textos_de_chave_e_provedor_fora_nao_citam_limite():
    assert "limite" not in MENSAGEM_CHAVE_RECUSADA.lower()
    assert "limite" not in MENSAGEM_PROVEDOR_FORA.lower()
    assert mensagem_da_falha_do_provedor(ValueError("x"), "geral") == "geral"
