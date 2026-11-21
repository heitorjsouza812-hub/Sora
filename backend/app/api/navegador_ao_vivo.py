"""Navegador do bot ao vivo para o app (Farol-2, item 18; ``app/navegador/ao_vivo.py``).

- ``POST /v1/agentes/{id}/navegador/assistir``: "estou olhando"; liga os quadros por 12 s
  (o app repete a cada ~5 s enquanto o painel estiver aberto). Sem isso o worker não captura;
- ``GET  /v1/navegador/abas/{aba_id}/captura``: última captura (JPEG, tamanho da janela);
- ``POST /v1/navegador/abas/{aba_id}/clicar|digitar|tecla|rolar``: o usuário age na aba que
  **assumiu** (``POST …/assumir``). 409 se a aba não estiver assumida.

Só o dono vê ou mexe (aba de outra conta, fechada ou sem captura = 404). O texto de ``digitar``
não é guardado, nem registrado, nem enviado em evento: só vai ao navegador.
"""

from __future__ import annotations

import base64
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis, usuario_atual
from app.ferramentas.base import ErroFerramenta
from app.modelos.tabelas import AbaNavegador, Agente
from app.navegador.ao_vivo import (
    CHAVE_ASSUMIDA,
    CHAVE_CAPTURA,
    CHAVE_DONO,
    MAX_TEXTO,
    TECLAS,
    Comando,
    enfileirar_comando,
    marcar_assistindo,
    validar_comando,
)

roteador = APIRouter(tags=["navegador"])
Usuario = Annotated[UUID, Depends(usuario_atual)]
Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]


class Assistindo(BaseModel):
    expira_em_segundos: int


class Enviado(BaseModel):
    enviado: bool = True


class CliqueEntrada(BaseModel):
    x: int = Field(ge=0, le=20_000, description="Posição na imagem que o usuário viu (px).")
    y: int = Field(ge=0, le=20_000)
    largura: int = Field(ge=1, le=20_000, description="Largura da imagem em que ele clicou.")
    altura: int = Field(ge=1, le=20_000, description="Altura da imagem em que ele clicou.")


class TextoEntrada(BaseModel):
    texto: str = Field(min_length=1, max_length=MAX_TEXTO, repr=False)


class TeclaEntrada(BaseModel):
    tecla: str = Field(description="Uma de: " + ", ".join(sorted(TECLAS)) + ".")


class RolagemEntrada(BaseModel):
    dy: int = Field(ge=-5_000, le=5_000, description="Pixels; negativo sobe.")


async def _conferir_bot(sessao: AsyncSession, usuario_id: UUID, agente_id: UUID) -> None:
    existe = await sessao.scalar(
        select(Agente.id).where(
            Agente.id == agente_id, Agente.usuario_id == usuario_id, Agente.apagado_em.is_(None)
        )
    )
    if existe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot não encontrado.")


async def _conferir_dono(
    sessao: AsyncSession, redis: Redis, usuario_id: UUID, aba_id: UUID
) -> None:
    """O worker grava o dono a cada quadro; sem quadro, vale a aba salva no banco."""
    dono = await redis.get(CHAVE_DONO.format(aba_id=aba_id))
    if dono is not None:
        if (dono.decode() if isinstance(dono, bytes) else dono) != str(usuario_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Aba não encontrada.")
        return
    existe = await sessao.scalar(
        select(AbaNavegador.id).where(
            AbaNavegador.id == aba_id, AbaNavegador.usuario_id == usuario_id
        )
    )
    if existe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aba não encontrada.")


@roteador.post("/agentes/{agente_id}/navegador/assistir")
async def assistir(
    agente_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> Assistindo:
    await _conferir_bot(sessao, usuario_id, agente_id)
    return Assistindo(expira_em_segundos=await marcar_assistindo(redis, agente_id))


@roteador.get(
    "/navegador/abas/{aba_id}/captura",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def captura_da_aba(
    aba_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> Response:
    await _conferir_dono(sessao, redis, usuario_id, aba_id)
    guardada = await redis.get(CHAVE_CAPTURA.format(aba_id=aba_id))
    if not guardada:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Ainda não há captura desta aba. Abra o painel do navegador e espere um instante.",
        )
    return Response(
        base64.b64decode(guardada),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


async def _enviar(
    aba_id: UUID, comando: Comando, sessao: AsyncSession, redis: Redis, usuario_id: UUID
) -> Enviado:
    await _conferir_dono(sessao, redis, usuario_id, aba_id)
    if not await redis.exists(CHAVE_ASSUMIDA.format(aba_id=aba_id)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Assuma a aba antes de clicar ou digitar nela."
        )
    try:
        validar_comando(comando)
        await enfileirar_comando(redis, aba_id, comando)
    except ErroFerramenta as erro:
        codigo = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if str(erro).startswith("Muitos")
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(codigo, str(erro)) from erro
    return Enviado()


@roteador.post("/navegador/abas/{aba_id}/clicar", status_code=status.HTTP_202_ACCEPTED)
async def clicar(
    aba_id: UUID, dados: CliqueEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> Enviado:
    comando = Comando(tipo="clicar", usuario_id=usuario_id, **dados.model_dump())
    return await _enviar(aba_id, comando, sessao, redis, usuario_id)


@roteador.post("/navegador/abas/{aba_id}/digitar", status_code=status.HTTP_202_ACCEPTED)
async def digitar(
    aba_id: UUID, dados: TextoEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> Enviado:
    comando = Comando(tipo="digitar", usuario_id=usuario_id, texto=dados.texto)
    return await _enviar(aba_id, comando, sessao, redis, usuario_id)


@roteador.post("/navegador/abas/{aba_id}/tecla", status_code=status.HTTP_202_ACCEPTED)
async def tecla(
    aba_id: UUID, dados: TeclaEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> Enviado:
    comando = Comando(tipo="tecla", usuario_id=usuario_id, tecla=dados.tecla)
    return await _enviar(aba_id, comando, sessao, redis, usuario_id)


@roteador.post("/navegador/abas/{aba_id}/rolar", status_code=status.HTTP_202_ACCEPTED)
async def rolar(
    aba_id: UUID, dados: RolagemEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> Enviado:
    comando = Comando(tipo="rolar", usuario_id=usuario_id, dy=dados.dy)
    return await _enviar(aba_id, comando, sessao, redis, usuario_id)


# ---------------------------------------------------------------- Ensinar (Onda 3, item 14)


class GravacaoSaida(BaseModel):
    gravando: bool
    passos: list[str]
    """Cada passo já em frase ("Clique em botão “Entrar”"), na ordem."""


class ConcluirEntrada(BaseModel):
    objetivo: str = Field(min_length=1, max_length=300, description="O que a tarefa faz.")


async def _aba_do_usuario(sessao: AsyncSession, usuario_id: UUID, aba_id: UUID) -> AbaNavegador:
    aba = await sessao.scalar(
        select(AbaNavegador).where(AbaNavegador.id == aba_id, AbaNavegador.usuario_id == usuario_id)
    )
    if aba is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aba não encontrada.")
    return aba


async def _gravacao(redis: Redis, aba_id: UUID) -> GravacaoSaida:
    from app.navegador import ensinar

    gravando = await ensinar.ensinando(redis, aba_id) is not None
    passos = ensinar.juntar_passos(await ensinar.ler(redis, aba_id)) if gravando else []
    return GravacaoSaida(gravando=gravando, passos=[ensinar.frase_do_passo(p) for p in passos])


@roteador.post("/navegador/abas/{aba_id}/ensinar")
async def comecar_a_ensinar(
    aba_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> GravacaoSaida:
    """Liga a gravação: o que o usuário fizer na aba assumida vira passos de uma habilidade."""
    from app.navegador import ensinar

    aba = await _aba_do_usuario(sessao, usuario_id, aba_id)
    if not await redis.exists(CHAVE_ASSUMIDA.format(aba_id=aba_id)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Assuma a aba antes de ensinar: a tarefa é feita por você."
        )
    url = aba.url if aba.url and not aba.url.startswith("about:") else None
    await ensinar.iniciar(redis, aba_id, usuario_id, aba.agente_id, url)
    return await _gravacao(redis, aba_id)


@roteador.get("/navegador/abas/{aba_id}/ensinar")
async def ver_gravacao(
    aba_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> GravacaoSaida:
    await _aba_do_usuario(sessao, usuario_id, aba_id)
    return await _gravacao(redis, aba_id)


@roteador.post("/navegador/abas/{aba_id}/ensinar/concluir")
async def concluir_ensino(
    aba_id: UUID, dados: ConcluirEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> dict[str, object]:
    """Para a gravação e devolve o **rascunho** da habilidade. Nada é salvo aqui: o app mostra
    o rascunho e o usuário salva (``POST /v1/habilidades``) depois de ler e ajustar."""
    from urllib.parse import urlsplit

    from app.navegador import ensinar

    aba = await _aba_do_usuario(sessao, usuario_id, aba_id)
    if await ensinar.ensinando(redis, aba_id) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A gravação não está ligada nesta aba.")
    passos = await ensinar.ler(redis, aba_id)
    inicio = next((p.url for p in passos if p.url), None) or aba.url
    dominio = (urlsplit(inicio).hostname or None) if inicio else None
    try:
        rascunho = ensinar.rascunho(passos, dados.objetivo, dominio)
    except ValueError as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro)) from erro
    await ensinar.encerrar(redis, aba_id)
    return rascunho.model_dump()


@roteador.delete("/navegador/abas/{aba_id}/ensinar", status_code=status.HTTP_204_NO_CONTENT)
async def cancelar_ensino(
    aba_id: UUID, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> None:
    from app.navegador import ensinar

    await _aba_do_usuario(sessao, usuario_id, aba_id)
    await ensinar.encerrar(redis, aba_id)
