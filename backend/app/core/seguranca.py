"""Senha argon2id, JWT de acesso, cifra AES-GCM e token de renovação; especificação §8.2."""

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

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


VERSAO_CHAVE = 1
"""Versão padrão da chave mestra (``CHAVE_MESTRA_VERSAO``), gravada no 1º byte do texto cifrado."""


def _chave_atual() -> tuple[int, bytes]:
    config = obter_configuracao()
    return config.chave_mestra_versao, config.chaveiro()[config.chave_mestra_versao]


def _chave_da_versao(versao: int) -> bytes:
    chave = obter_configuracao().chaveiro().get(versao)
    if chave is None:
        raise ValueError("Versão da chave de cifra desconhecida.")
    return chave


def _aad(usuario_id: UUID, provedor: str) -> bytes:
    return f"{usuario_id}:{provedor}".encode()


def cifrar_segredo(valor: str, *, usuario_id: UUID, provedor: str) -> bytes:
    """Cifra uma chave de provedor com AES-GCM.

    Formato: ``versão da chave (1 byte) + nonce (12 bytes) + texto cifrado``. O AAD é
    ``usuario_id:provedor``, então o texto cifrado de um usuário/provedor não decifra em outra
    linha do banco (copiar a coluna entre contas não funciona). Cifra sempre com a chave atual.
    """
    versao, chave = _chave_atual()
    nonce = os.urandom(TAMANHO_NONCE)
    cifrado = AESGCM(chave).encrypt(nonce, valor.encode(), _aad(usuario_id, provedor))
    return bytes([versao]) + nonce + cifrado


def decifrar_segredo(valor: bytes, *, usuario_id: UUID, provedor: str) -> str:
    """Decifra o que ``cifrar_segredo`` gravou, exigindo o mesmo usuário e provedor.

    A chave é escolhida pela versão do 1º byte (a atual ou uma de ``CHAVES_MESTRAS_ANTIGAS``).
    """
    if not valor:
        raise ValueError("Versão da chave de cifra desconhecida.")
    chave = _chave_da_versao(valor[0])
    nonce = valor[1 : 1 + TAMANHO_NONCE]
    cifrado = valor[1 + TAMANHO_NONCE :]
    return AESGCM(chave).decrypt(nonce, cifrado, _aad(usuario_id, provedor)).decode()


def precisa_recifrar(valor: bytes) -> bool:
    """O texto cifrado usa uma chave que não é a atual?"""
    return bool(valor) and valor[0] != obter_configuracao().chave_mestra_versao


def recifrar_segredo(valor: bytes, *, usuario_id: UUID, provedor: str) -> bytes:
    """Decifra com a chave da versão gravada e cifra de novo com a atual (migração da rotação).

    Já na versão atual: devolve o mesmo valor. Depois de recifrar todas as linhas, a chave
    antiga pode sair de ``CHAVES_MESTRAS_ANTIGAS``.
    """
    if not precisa_recifrar(valor):
        decifrar_segredo(valor, usuario_id=usuario_id, provedor=provedor)  # confere integridade
        return valor
    texto = decifrar_segredo(valor, usuario_id=usuario_id, provedor=provedor)
    return cifrar_segredo(texto, usuario_id=usuario_id, provedor=provedor)


def hash_token(token: str) -> str:
    """sha256 em hexadecimal; é o que fica no banco."""
    return hashlib.sha256(token.encode()).hexdigest()


def gerar_token_renovacao() -> tuple[str, str]:
    """Gera o token aleatório (32 bytes) e seu hash persistível."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)
