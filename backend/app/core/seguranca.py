"""Senha argon2id, JWT de acesso, cifra AES-GCM e token de renovação; especificação §8.2."""

import base64
import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import obter_configuracao

SENHA_TAMANHO_MINIMO = 10
ACESSO_VALIDADE = timedelta(minutes=15)
RENOVACAO_VALIDADE = timedelta(days=30)
ALGORITMO_JWT = "HS256"
TAMANHO_NONCE = 12

_hasher = PasswordHash((Argon2Hasher(),))


class ErroSenhaFraca(ValueError):
    """A senha não atinge o mínimo de caracteres."""


class ErroToken(Exception):
    """O token de acesso é inválido ou expirou."""


def validar_senha(senha: str) -> None:
    """Exige o mínimo de 10 caracteres da §8.2."""
    if len(senha) < SENHA_TAMANHO_MINIMO:
        raise ErroSenhaFraca(f"A senha precisa ter ao menos {SENHA_TAMANHO_MINIMO} caracteres.")


def gerar_hash_senha(senha: str) -> str:
    """Gera hash argon2id de uma senha válida."""
    validar_senha(senha)
    return _hasher.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Compara uma senha com seu hash sem registrar dados sensíveis."""
    try:
        return _hasher.verify(senha, senha_hash)
    except Exception:
        return False


def criar_token_acesso(dados: dict[str, Any], validade: timedelta = ACESSO_VALIDADE) -> str:
    """Assina um JWT de acesso de curta duração."""
    agora = datetime.now(UTC)
    carga = {**dados, "iat": agora, "exp": agora + validade}
    segredo = obter_configuracao().jwt_segredo.get_secret_value()
    return jwt.encode(carga, segredo, algorithm=ALGORITMO_JWT)


def decodificar_token_acesso(token: str) -> dict[str, Any]:
    """Valida assinatura e validade do JWT de acesso."""
    segredo = obter_configuracao().jwt_segredo.get_secret_value()
    try:
        return jwt.decode(token, segredo, algorithms=[ALGORITMO_JWT], options={"require": ["exp"]})
    except jwt.PyJWTError as erro:
        raise ErroToken("Token de acesso inválido ou expirado.") from erro


def _chave_mestra() -> bytes:
    bruta = obter_configuracao().chave_mestra.get_secret_value()
    chave = base64.b64decode(bruta, validate=True)
    if len(chave) != 32:
        raise ValueError("CHAVE_MESTRA precisa ter 32 bytes em base64.")
    return chave


def cifrar_segredo(valor: str) -> bytes:
    """Cifra uma chave de provedor usando AES-GCM (nonce de 12 bytes + texto cifrado)."""
    nonce = os.urandom(TAMANHO_NONCE)
    return nonce + AESGCM(_chave_mestra()).encrypt(nonce, valor.encode(), None)


def decifrar_segredo(valor: bytes) -> str:
    """Decifra uma chave de provedor previamente protegida."""
    nonce, cifrado = valor[:TAMANHO_NONCE], valor[TAMANHO_NONCE:]
    return AESGCM(_chave_mestra()).decrypt(nonce, cifrado, None).decode()


def hash_token(token: str) -> str:
    """sha256 em hexadecimal; é o que fica no banco."""
    return hashlib.sha256(token.encode()).hexdigest()


def gerar_token_renovacao() -> tuple[str, str]:
    """Gera o token aleatório (32 bytes) e seu hash persistível."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)
