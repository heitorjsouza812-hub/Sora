"""Carrega variáveis de ambiente da fase 1; especificação §8.3."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracao(BaseSettings):
    """Configuração validada do processo da API ou do worker."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ambiente: Literal["desenvolvimento", "teste", "producao"] = "desenvolvimento"
    database_url: str
    redis_url: str
    chave_mestra: SecretStr
    jwt_segredo: SecretStr
    busca_provedor: str = "tavily"
    busca_chave: SecretStr | None = None
    app_url: str = "http://localhost:5173"
    cors_origens: str = "http://localhost:5173,http://tauri.localhost,tauri://localhost"
    sentry_dsn: str | None = None
    sora_modelo_falso: bool = False


@lru_cache
def obter_configuracao() -> Configuracao:
    """Obtém uma instância única da configuração validada."""
    return Configuracao()  # type: ignore[call-arg]
