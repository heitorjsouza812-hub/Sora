"""Ponto de entrada FastAPI e verificação de saúde; especificação §§2 e 8.3."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import roteador_v1
from app.core.config import obter_configuracao
from app.core.contas import ErroConta
from app.core.redis import criar_cliente_redis


def _trava_local(ambiente: str, ligado: bool) -> None:
    if ambiente == "producao" and ligado:
        raise RuntimeError("SORA_MODELO_FALSO=1 não é permitido em produção.")


try:  # a Bússola cria a função em app/llm/falso.py; até lá vale a mesma regra aqui
    from app.llm.falso import verificar_modelo_falso_permitido
except ImportError:
    verificar_modelo_falso_permitido = _trava_local


@asynccontextmanager
async def ciclo_de_vida(aplicacao: FastAPI) -> AsyncIterator[None]:
    """Recusa subir com o modelo falso em produção e abre/fecha o Redis da API."""
    config = obter_configuracao()
    verificar_modelo_falso_permitido(config.ambiente, config.sora_modelo_falso)
    aplicacao.state.redis = criar_cliente_redis(config.redis_url)
    try:
        yield
    finally:
        await aplicacao.state.redis.aclose()


async def tratar_erro_conta(_: Request, erro: ErroConta) -> JSONResponse:
    return JSONResponse({"detail": erro.detalhe}, erro.status_code, headers=erro.headers)


def criar_aplicacao() -> FastAPI:
    """Cria a aplicação HTTP e registra as rotas públicas da fase 1."""
    aplicacao = FastAPI(title="Sora Backend", version="0.1.0", lifespan=ciclo_de_vida)
    aplicacao.add_exception_handler(ErroConta, tratar_erro_conta)
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
