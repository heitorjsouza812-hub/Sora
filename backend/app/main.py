"""Ponto de entrada FastAPI e verificação de saúde; especificação §§2 e 8.3."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import roteador_v1
from app.busca.provedor import verificar_busca_permitida
from app.core.config import obter_configuracao
from app.core.contas import ErroConta
from app.core.corpo import LimiteDeCorpo
from app.core.observabilidade import configurar_log, iniciar_sentry
from app.core.redis import criar_cliente_redis
from app.core.saude import verificar_prontidao
from app.llm.falso import verificar_modelo_falso_permitido


@asynccontextmanager
async def ciclo_de_vida(aplicacao: FastAPI) -> AsyncIterator[None]:
    """Recusa subir com modelo ou busca falsos em produção e abre/fecha o Redis da API."""
    config = obter_configuracao()
    verificar_modelo_falso_permitido(config.ambiente, config.sora_modelo_falso)
    verificar_busca_permitida(config.busca_provedor, config.ambiente)
    configurar_log()
    iniciar_sentry(config, "api")
    aplicacao.state.redis = criar_cliente_redis(config.redis_url)
    try:
        yield
    finally:
        await aplicacao.state.redis.aclose()


async def tratar_erro_conta(_: Request, erro: ErroConta) -> JSONResponse:
    return JSONResponse({"detail": erro.detalhe}, erro.status_code, headers=erro.headers)


async def tratar_erro_validacao(_: Request, erro: RequestValidationError) -> JSONResponse:
    """Devolve metadados úteis sem ecoar senhas, chaves ou qualquer entrada do usuário."""
    detalhes = [
        {campo: item[campo] for campo in ("loc", "msg", "type") if campo in item}
        for item in erro.errors()
    ]
    return JSONResponse({"detail": detalhes}, status_code=422)


def criar_aplicacao() -> FastAPI:
    """Cria a aplicação HTTP e registra as rotas públicas da fase 1."""
    aplicacao = FastAPI(title="Sora Backend", version="0.1.0", lifespan=ciclo_de_vida)
    aplicacao.add_exception_handler(ErroConta, tratar_erro_conta)
    aplicacao.add_exception_handler(RequestValidationError, tratar_erro_validacao)
    aplicacao.add_middleware(
        CORSMiddleware,
        allow_origins=obter_configuracao().origens_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Last-Event-ID"],
    )
    # Por último = mais por fora: o corpo grande é recusado antes de qualquer rota ler o multipart.
    aplicacao.add_middleware(LimiteDeCorpo)
    aplicacao.include_router(roteador_v1, prefix="/v1")
    # /b/<código>: prévia do bot compartilhado para redes sociais (o Caddy manda /b/* para a API)
    from app.api.compartilhar import roteador_pagina

    aplicacao.include_router(roteador_pagina)

    @aplicacao.get("/health", tags=["saude"])
    async def health() -> dict[str, str]:
        """Vivo: o processo responde (não toca no banco nem no Redis)."""
        return {"status": "ok"}

    @aplicacao.get("/health/pronto", tags=["saude"])
    async def pronto(requisicao: Request) -> JSONResponse:
        """Pronto para atender: banco e Redis respondem em até 3 s. 503 se algum não responder
        (o healthcheck do Compose e o balanceador usam esta; ``/health`` não derruba o
        contêiner por um banco lento)."""
        return await verificar_prontidao(requisicao.app)

    return aplicacao


app = criar_aplicacao()
