"""Carrega variáveis de ambiente da fase 1; especificação §8.3.

Segura por padrão: sem ``AMBIENTE``, vale ``producao`` (cookie ``Secure``, modelo falso
proibido, segredos fortes, CORS sem localhost, sem API de modelos na rede local). O
desenvolvimento e os testes declaram ``AMBIENTE=desenvolvimento`` ou ``AMBIENTE=teste``
(``backend/.env.example``).
"""

import base64
import binascii
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.busca.provedor import NomeProvedor

_PREFIXO_URL = re.compile(r"^(postgres|postgresql)(\+\w+)?://")

AMBIENTES_LOCAIS = frozenset({"desenvolvimento", "teste"})
"""Ambientes em que valem os padrões de desenvolvimento (rede local, CORS do Vite)."""

JWT_SEGREDO_MINIMO = 32
"""Bytes mínimos do ``JWT_SEGREDO`` em produção (HS256; RFC 7518 §3.2)."""

_SEGREDOS_DE_EXEMPLO = ("troque", "change", "exemplo", "example", "placeholder")
"""Trechos de valores de exemplo que nunca valem como ``JWT_SEGREDO`` em produção."""

_ORIGENS_DESKTOP = ("http://tauri.localhost", "tauri://localhost")
_ORIGENS_DEV = ("http://localhost:5173", *_ORIGENS_DESKTOP)
_HOST_LOCAL = re.compile(r"^https?://(localhost|127\.|\[::1\])", re.IGNORECASE)
_LIGADOS = frozenset({"1", "true", "sim", "yes", "on"})
_DESLIGADOS = frozenset({"", "0", "false", "nao", "não", "no", "off"})


def _com_prefixo(url: str, prefixo: str) -> str:
    if not _PREFIXO_URL.match(url):
        raise ValueError("DATABASE_URL deve começar com postgresql:// (ou postgres://).")
    return _PREFIXO_URL.sub(prefixo, url, count=1)


def url_sqlalchemy(url: str) -> str:
    """URL do SQLAlchemy assíncrono (``postgresql+asyncpg://``)."""
    return _com_prefixo(url, "postgresql+asyncpg://")


def url_psycopg(url: str) -> str:
    """URL do checkpointer do LangGraph (psycopg 3, ``postgresql://``)."""
    return _com_prefixo(url, "postgresql://")


def url_pg_dump(url: str) -> str:
    """URL para ``pg_dump``/``psql`` (libpq, ``postgresql://``)."""
    return _com_prefixo(url, "postgresql://")


def ambiente_local(ambiente: str) -> bool:
    """``desenvolvimento`` ou ``teste``; qualquer outro valor conta como produção."""
    return ambiente.strip().lower() in AMBIENTES_LOCAIS


def chave_mestra_bytes(bruta: str) -> bytes:
    """Decodifica a ``CHAVE_MESTRA`` (base64 de 32 bytes) ou levanta ``ValueError``."""
    try:
        chave = base64.b64decode(bruta, validate=True)
    except (binascii.Error, ValueError) as erro:
        raise ValueError("CHAVE_MESTRA precisa ser base64 válido.") from erro
    if len(chave) != 32:
        raise ValueError("CHAVE_MESTRA precisa ter 32 bytes em base64.")
    return chave


def montar_chaveiro(atual: str, versao_atual: int, antigas: str = "") -> dict[int, bytes]:
    """Versão (1 a 255, o 1º byte do texto cifrado) → chave de 32 bytes.

    ``antigas`` é ``"1:<base64>,2:<base64>"``; vazio = sem chaves aposentadas. Versão repetida,
    fora da faixa ou chave inválida levanta ``ValueError`` (o boot falha).
    """
    if not 1 <= versao_atual <= 255:
        raise ValueError("CHAVE_MESTRA_VERSAO precisa estar entre 1 e 255.")
    chaveiro = {versao_atual: chave_mestra_bytes(atual)}
    for item in (parte.strip() for parte in antigas.split(",")):
        if not item:
            continue
        versao_texto, separador, bruta = item.partition(":")
        if not separador or not versao_texto.strip().isdigit():
            raise ValueError(
                "CHAVES_MESTRAS_ANTIGAS deve ser '<versão>:<base64>' separados por vírgula."
            )
        versao = int(versao_texto)
        if not 1 <= versao <= 255:
            raise ValueError("Versões de CHAVES_MESTRAS_ANTIGAS precisam estar entre 1 e 255.")
        if versao in chaveiro:
            raise ValueError(f"Versão {versao} da chave mestra repetida.")
        chaveiro[versao] = chave_mestra_bytes(bruta.strip())
    return chaveiro


class Configuracao(BaseSettings):
    """Configuração validada do processo da API ou do worker (falha no boot, não no uso)."""

    # env_ignore_empty: `VAR=` no .env (como no .env.example) vale "não definida".
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    ambiente: Literal["desenvolvimento", "teste", "producao"] = "producao"
    database_url: str
    redis_url: str
    chave_mestra: SecretStr
    """Chave mestra ATUAL (cifra e decifra); a versão dela é ``CHAVE_MESTRA_VERSAO``."""
    chave_mestra_versao: int = 1
    chaves_mestras_antigas: SecretStr | None = None
    """Chaves aposentadas, só para decifrar: ``"1:<base64>,2:<base64>"`` (rotação, VAL-17)."""
    jwt_segredo: SecretStr
    busca_provedor: NomeProvedor = "tavily"
    busca_chave: SecretStr | None = None
    app_url: str = "http://localhost:5173"
    cors_origens: str | None = None
    """Lista separada por vírgula. Vazio: Vite + Tauri fora de produção; em produção,
    ``APP_URL`` (se não for local) + Tauri."""
    sentry_dsn: str | None = None
    sora_modelo_falso: bool = False
    permitir_provedor_rede_local: bool | None = None
    """API de modelos em localhost/rede privada (Ollama, servidor na LAN). Vazio: liberado
    em desenvolvimento/teste, proibido em produção."""
    pasta_arquivos: Path = Path("arquivos")
    """Volume dos anexos (``/srv/sora/arquivos`` no contêiner, relativo a ``/srv/sora``).
    ``anexos.caminho`` é relativo a esta pasta."""

    @field_validator("sora_modelo_falso", mode="before")
    @classmethod
    def _ligado(cls, valor: object) -> object:
        """Aceita os mesmos valores que ``app.llm.falso`` (inclusive ``sim``)."""
        if isinstance(valor, str):
            texto = valor.strip().lower()
            if texto in _LIGADOS:
                return True
            if texto in _DESLIGADOS:
                return False
        return valor

    @model_validator(mode="after")
    def _seguranca(self) -> Self:
        self.chaveiro()
        if ambiente_local(self.ambiente):
            return self
        segredo = self.jwt_segredo.get_secret_value()
        if len(segredo.encode()) < JWT_SEGREDO_MINIMO:
            raise ValueError(
                f"JWT_SEGREDO precisa ter ao menos {JWT_SEGREDO_MINIMO} bytes em produção."
            )
        if any(trecho in segredo.lower() for trecho in _SEGREDOS_DE_EXEMPLO):
            raise ValueError("JWT_SEGREDO parece um valor de exemplo; gere um aleatório.")
        if any(_HOST_LOCAL.match(origem) for origem in self._origens_informadas()):
            raise ValueError("CORS_ORIGENS não pode ter localhost em produção.")
        return self

    def chaveiro(self) -> dict[int, bytes]:
        """Versão → chave mestra (a atual + as antigas), validado no boot."""
        return montar_chaveiro(
            self.chave_mestra.get_secret_value(),
            self.chave_mestra_versao,
            self.chaves_mestras_antigas.get_secret_value() if self.chaves_mestras_antigas else "",
        )

    def _origens_informadas(self) -> list[str]:
        return [o.strip() for o in (self.cors_origens or "").split(",") if o.strip()]

    @property
    def producao(self) -> bool:
        return not ambiente_local(self.ambiente)

    @property
    def origens_cors(self) -> list[str]:
        """Origens liberadas no CORS (com credenciais)."""
        if informadas := self._origens_informadas():
            return informadas
        if not self.producao:
            return list(_ORIGENS_DEV)
        app = [] if _HOST_LOCAL.match(self.app_url) else [self.app_url.rstrip("/")]
        return [*app, *_ORIGENS_DESKTOP]

    @property
    def rede_local_permitida(self) -> bool:
        """Pode falar com API de modelos em localhost/rede privada?"""
        if self.permitir_provedor_rede_local is None:
            return not self.producao
        return self.permitir_provedor_rede_local

    @property
    def database_url_sqlalchemy(self) -> str:
        return url_sqlalchemy(self.database_url)

    @property
    def database_url_psycopg(self) -> str:
        return url_psycopg(self.database_url)

    @property
    def database_url_pg_dump(self) -> str:
        return url_pg_dump(self.database_url)


@lru_cache
def obter_configuracao() -> Configuracao:
    """Obtém uma instância única da configuração validada."""
    return Configuracao()  # type: ignore[call-arg]
