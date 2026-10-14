"""Ponto de entrada FastAPI e verificação de saúde; especificação §§2 e 8.3."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import roteador_v1
from app.core.config import obter_configuracao


def criar_aplicacao() -> FastAPI:
    """Cria a aplicação HTTP e registra as rotas públicas da fase 1."""
    aplicacao = FastAPI(title="Sora Backend", version="0.1.0")
    origens = [o.strip() for o in obter_configuracao().cors_origens.split(",") if o.strip()]
    aplicacao.add_middleware(
        CORSMiddleware,
        allow_origins=origens,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Last-Event-ID"],
    )
    aplicacao.include_router(roteador_v1, prefix="/v1")

    @aplicacao.get("/health", tags=["saude"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return aplicacao


app = criar_aplicacao()
