"""Voz com a chave do próprio usuário (Relógio, etapa 4): transcrever o microfone e falar uma
resposta. Usa o provedor OpenAI (ou compatível com ``base_url``) que ele já conectou em
Configurações → Modelos de IA; sem provedor, 404. A chave nunca sai do servidor."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.dependencias import usuario_atual
from app.llm.provedores import (
    DestinoBloqueado,
    ErroProvedor,
    criar_cliente_listagem,
    listar_modelos,
    politica_de_rede,
    validar_base_url,
)
from app.modelos.enumeracoes import TipoProvedor
from app.modelos.tabelas import Provedor
from app.seletor.repositorio import config_do_provedor
from app.voz.modelos import (
    FALA_FALLBACK,
    TRANSCRICAO_FALLBACK,
    modelo_de_fala,
    modelo_de_transcricao,
)
from app.voz.provedores import MAX_BYTES_AUDIO, PRAZO_SEGUNDOS, ErroVoz, VozOpenAI
from app.voz.texto import falavel

roteador = APIRouter(prefix="/voz", tags=["voz"])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
UsuarioId = Annotated[UUID, Depends(usuario_atual)]


SEM_MODELO_FALA = (
    "O provedor conectado não oferece voz para falar. Conecte uma chave da OpenAI em "
    "Configurações → Modelos de IA para usar a voz."
)
SEM_MODELO_TRANSCRICAO = (
    "O provedor conectado não oferece transcrição. Conecte uma chave da OpenAI em "
    "Configurações → Modelos de IA para usar a voz."
)


class Fala(BaseModel):
    texto: str = Field(min_length=1, max_length=8_000)
    voz: str = Field(default="alloy", max_length=40)


class Transcricao(BaseModel):
    texto: str


async def _voz_do_usuario(
    sessao: AsyncSession, usuario_id: UUID, uso: Literal["transcricao", "fala"]
) -> VozOpenAI:
    provedor_id = await sessao.scalar(
        select(Provedor.id)
        .where(
            Provedor.usuario_id == usuario_id,
            Provedor.tipo.in_([TipoProvedor.OPENAI, TipoProvedor.COMPATIVEL_OPENAI]),
            Provedor.apagado_em.is_(None),
            Provedor.chave_cifrada.is_not(None),
        )
        .order_by(Provedor.tipo)  # "compativel_openai" < "openai": prefere o OpenAI de verdade
        .limit(1)
    )
    if provedor_id is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Conecte uma chave da OpenAI em Configurações → Modelos de IA para usar a voz.",
        )
    config = await config_do_provedor(sessao, usuario_id, provedor_id)
    politica = politica_de_rede()
    try:
        base = validar_base_url(config.tipo, config.base_url, politica)
    except DestinoBloqueado as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro)) from erro
    # Mesmo transporte dos provedores: conecta só em IP público, conferido na hora da conexão
    # (anti DNS rebinding), sem seguir redirecionamento nem proxy do ambiente.
    cliente = criar_cliente_listagem(politica)
    cliente.timeout = httpx.Timeout(PRAZO_SEGUNDOS, connect=10.0)
    voz = VozOpenAI(config.api_key.get_secret_value() if config.api_key else "", cliente=cliente)
    if base:
        voz.api = base
    if config.tipo is TipoProvedor.COMPATIVEL_OPENAI:
        await _escolher_modelo(voz, config, cliente, politica, uso)
    return voz


async def _escolher_modelo(voz, config, cliente, politica, uso) -> None:  # type: ignore[no-untyped-def]
    """Provedor compatível (Groq etc.): o modelo vem da lista dele, não do da OpenAI."""
    try:
        nomes = await listar_modelos(config, cliente=cliente, politica=politica)
    except ErroProvedor:  # lista indisponível: tenta o nome mais comum
        voz.modelo_transcricao = TRANSCRICAO_FALLBACK
        voz.modelo_fala = FALA_FALLBACK
        return
    if uso == "transcricao":
        modelo = modelo_de_transcricao(nomes)
        if modelo is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, SEM_MODELO_TRANSCRICAO)
        voz.modelo_transcricao = modelo
    else:
        modelo = modelo_de_fala(nomes)
        if modelo is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, SEM_MODELO_FALA)
        voz.modelo_fala = modelo


@roteador.post("/transcrever")
async def transcrever(
    usuario_id: UsuarioId,
    sessao: Sessao,
    audio: Annotated[UploadFile, File()],
    idioma: Annotated[str, Form(max_length=8)] = "pt",
) -> Transcricao:
    voz = await _voz_do_usuario(sessao, usuario_id, "transcricao")
    conteudo = await audio.read(MAX_BYTES_AUDIO + 1)
    if not conteudo:
        raise HTTPException(422, "O áudio veio vazio.")
    if len(conteudo) > MAX_BYTES_AUDIO:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "O áudio é grande demais.")
    try:
        texto = await voz.transcrever(conteudo, audio.content_type or "audio/webm", idioma)
    except ErroVoz as erro:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(erro)) from erro
    return Transcricao(texto=texto)


@roteador.post("/falar")
async def falar_texto(dados: Fala, usuario_id: UsuarioId, sessao: Sessao) -> Response:
    voz = await _voz_do_usuario(sessao, usuario_id, "fala")
    texto = falavel(dados.texto)
    try:
        audio = await voz.sintetizar(texto or dados.texto, dados.voz)
    except ErroVoz as erro:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(erro)) from erro
    return Response(audio.conteudo, media_type=audio.tipo)
