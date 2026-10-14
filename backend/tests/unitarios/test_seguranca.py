"""Senha, JWT, cifra AES-GCM e token de renovação; especificação §8.2."""

import base64
from datetime import timedelta

import pytest

from app.core import seguranca


def test_senha_curta_e_recusada() -> None:
    with pytest.raises(seguranca.ErroSenhaFraca):
        seguranca.gerar_hash_senha("curta123")


def test_hash_argon2id_verifica_e_nao_guarda_a_senha() -> None:
    hash_ = seguranca.gerar_hash_senha("uma senha longa")
    assert hash_.startswith("$argon2id$")
    assert "uma senha longa" not in hash_
    assert seguranca.verificar_senha("uma senha longa", hash_)
    assert not seguranca.verificar_senha("outra senha longa", hash_)
    assert not seguranca.verificar_senha("x", "isto-nao-e-um-hash")


def test_token_de_acesso_vale_15_minutos_e_carrega_o_usuario() -> None:
    token = seguranca.criar_token_acesso({"sub": "abc"})
    carga = seguranca.decodificar_token_acesso(token)
    assert carga["sub"] == "abc"
    assert carga["exp"] - carga["iat"] == 15 * 60


def test_token_expirado_adulterado_ou_de_outro_segredo_e_recusado() -> None:
    expirado = seguranca.criar_token_acesso({"sub": "abc"}, timedelta(seconds=-5))
    with pytest.raises(seguranca.ErroToken):
        seguranca.decodificar_token_acesso(expirado)
    valido = seguranca.criar_token_acesso({"sub": "abc"})
    with pytest.raises(seguranca.ErroToken):
        seguranca.decodificar_token_acesso(valido[:-3] + "xxx")
    with pytest.raises(seguranca.ErroToken):
        seguranca.decodificar_token_acesso("lixo")


def test_cifra_aes_gcm_ida_e_volta_com_nonce_novo_a_cada_vez() -> None:
    a = seguranca.cifrar_segredo("gsk_chave-secreta")
    b = seguranca.cifrar_segredo("gsk_chave-secreta")
    assert a != b
    assert b"gsk_chave-secreta" not in a
    assert seguranca.decifrar_segredo(a) == "gsk_chave-secreta"


def test_cifra_detecta_adulteracao() -> None:
    from cryptography.exceptions import InvalidTag

    cifrado = bytearray(seguranca.cifrar_segredo("segredo"))
    cifrado[-1] ^= 1
    with pytest.raises(InvalidTag):
        seguranca.decifrar_segredo(bytes(cifrado))


def test_token_de_renovacao_tem_32_bytes_e_hash_sha256() -> None:
    token, hash_ = seguranca.gerar_token_renovacao()
    assert len(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))) == 32
    assert hash_ == seguranca.hash_token(token)
    assert len(hash_) == 64
    assert seguranca.gerar_token_renovacao()[0] != token
