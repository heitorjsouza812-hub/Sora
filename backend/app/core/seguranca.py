"""Contratos de argon2id, JWT e AES-GCM; especificação §8.2."""

from datetime import timedelta
from typing import Any


def gerar_hash_senha(senha: str) -> str:
    """Gera hash argon2id de uma senha válida."""
    raise NotImplementedError


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Compara uma senha com seu hash sem registrar dados sensíveis."""
    raise NotImplementedError


def criar_token_acesso(dados: dict[str, Any], validade: timedelta) -> str:
    """Assina um JWT de acesso de curta duração."""
    raise NotImplementedError


def cifrar_segredo(valor: str) -> bytes:
    """Cifra uma chave de provedor usando AES-GCM."""
    raise NotImplementedError


def decifrar_segredo(valor: bytes) -> str:
    """Decifra uma chave de provedor previamente protegida."""
    raise NotImplementedError


def gerar_token_renovacao() -> tuple[str, str]:
    """Gera o token aleatório e seu hash persistível."""
    raise NotImplementedError
