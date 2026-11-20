"""Rotas da conta autenticada e LGPD; especificação §8.2."""

import asyncio
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import FileResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.api.auth import CAMINHO_COOKIE, COOKIE_RENOVACAO, soltar_pc_das_sessoes
from app.core import contas
from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import obter_redis, sessao_de_login_atual, usuario_atual
from app.core.exportacao import LIMITE_POR_HORA as LIMITE_EXPORTACAO
from app.core.exportacao import gerar_exportacao
from app.core.redis import verificar_limite
from app.modelos.esquemas import (
    ApagarContaEntrada,
    ContaSaida,
    ExportarDadosEntrada,
    TrocarSenhaEntrada,
)

roteador = APIRouter(tags=["conta"])


@roteador.get("/eu")
async def obter_eu(
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(obter_sessao, scope="function")],
) -> ContaSaida:
    """Retorna dados mínimos da conta e do onboarding."""
    usuario, tem_provedor = await contas.dados_da_conta(sessao, usuario_id)
    return ContaSaida(
        nome=usuario.nome,
        email=usuario.email,
        prioridade=usuario.prioridade,
        tem_provedor=tem_provedor,
    )


@roteador.post("/conta/senha", status_code=status.HTTP_204_NO_CONTENT)
async def trocar_senha(
    dados: TrocarSenhaEntrada,
    requisicao: Request,
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(obter_sessao, scope="function")],
    redis: Annotated[Redis, Depends(obter_redis)],
) -> None:
    """Troca a senha conferindo a atual; os outros aparelhos saem, este continua entrado."""
    encerradas = await contas.trocar_senha(
        sessao,
        redis,
        usuario_id,
        sessao_de_login_atual(requisicao),
        dados.senha_atual,
        dados.senha_nova,
    )
    await soltar_pc_das_sessoes(redis, usuario_id, encerradas)


def _arquivo_temporario() -> Path:
    descritor, nome = tempfile.mkstemp(prefix="sora-exportacao-", suffix=".zip")
    os.close(descritor)
    return Path(nome)


@roteador.post("/conta/exportar", response_class=FileResponse)
async def exportar_dados(
    dados: ExportarDadosEntrada,
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(obter_sessao, scope="function")],
    redis: Annotated[Redis, Depends(obter_redis)],
) -> FileResponse:
    """Baixa um ``.zip`` com todos os dados da conta (LGPD), depois de confirmar a senha."""
    await contas.conferir_senha(sessao, redis, usuario_id, dados.senha, f"exportar:{usuario_id}")
    espera = await verificar_limite(redis, f"exportar:feitas:{usuario_id}", *LIMITE_EXPORTACAO)
    if espera:
        raise contas.ErroLimite(espera)
    agora = datetime.now(UTC)
    destino = await asyncio.to_thread(_arquivo_temporario)
    try:
        await gerar_exportacao(
            sessao, usuario_id, destino, obter_configuracao().pasta_arquivos, agora
        )
    except BaseException:
        await asyncio.to_thread(destino.unlink, missing_ok=True)
        raise
    return FileResponse(
        destino,
        media_type="application/zip",
        filename=f"sora-meus-dados-{agora:%Y-%m-%d}.zip",
        background=BackgroundTask(destino.unlink, missing_ok=True),
        headers={"Cache-Control": "no-store"},
    )


@roteador.delete("/conta", status_code=status.HTTP_204_NO_CONTENT)
async def apagar_conta(
    dados: ApagarContaEntrada,
    resposta: Response,
    usuario_id: Annotated[UUID, Depends(usuario_atual)],
    sessao: Annotated[AsyncSession, Depends(obter_sessao, scope="function")],
    redis: Annotated[Redis, Depends(obter_redis)],
) -> None:
    """Apaga os dados pertencentes ao usuário após confirmar a senha."""
    await contas.apagar_conta(sessao, usuario_id, dados.senha, redis=redis)
    resposta.delete_cookie(COOKIE_RENOVACAO, path=CAMINHO_COOKIE)
