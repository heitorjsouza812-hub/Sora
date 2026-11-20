""" "Relatar problema": o usuário conta o que houve e o app manda um diagnóstico sem dado pessoal.

O diagnóstico é o que o app consegue ver sem ler conversa nenhuma: versão, plataforma, tela atual,
tamanho da janela e os últimos erros. O servidor mascara de novo antes de gravar (CPF, cartão,
senha, tokens e chaves, como nos canais da empresa; e-mails também, no diagnóstico). O usuário vê
os próprios relatos e pode retirar qualquer um (a linha é apagada). O time lê pelo CLI
(``python -m app.cli relatos listar``); com Sentry ligado, chega também um aviso sem o texto.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.canais_empresa.pii import mascarar_pii
from app.core.banco import obter_sessao
from app.core.contas import ErroLimite
from app.core.dependencias import obter_redis, usuario_atual
from app.core.redis import verificar_limite
from app.modelos.esquemas import EsquemaBase
from app.modelos.tabelas import Relato

registro = logging.getLogger(__name__)

roteador = APIRouter(prefix="/relatos", tags=["relatos"])

Usuario = Annotated[UUID, Depends(usuario_atual)]
Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
RedisDep = Annotated[Redis, Depends(obter_redis)]

LIMITE_RELATOS = (10, 60 * 60)
"""Relatos por usuário por hora."""
MAX_LISTA = 50

_EMAIL = re.compile(r"[^\s@<>()\"']+@[^\s@<>()\"']+\.[A-Za-z]{2,}")
MASCARA_EMAIL = "[e-mail]"


class ErroRecente(EsquemaBase):
    quando: datetime
    origem: Literal["janela", "promessa", "api", "app"]
    mensagem: str = Field(max_length=500)


class Diagnostico(EsquemaBase):
    versao_app: str = Field(max_length=40)
    plataforma: Literal["web", "desktop", "celular"]
    rota: str = Field(max_length=200)
    navegador: str = Field(max_length=300)
    tela: str = Field(max_length=20)
    idioma: str = Field(max_length=20)
    erros: list[ErroRecente] = Field(default_factory=list, max_length=20)


class RelatoEntrada(EsquemaBase):
    texto: str = Field(min_length=1, max_length=4_000)
    diagnostico: Diagnostico | None = None


class RelatoSaida(EsquemaBase):
    id: UUID
    resumo: str
    com_diagnostico: bool
    criado_em: datetime


def mascarar_diagnostico(valor: Any) -> Any:
    """Máscara de PII em cada texto do diagnóstico, e e-mails também (o app não precisa deles)."""
    if isinstance(valor, str):
        return _EMAIL.sub(MASCARA_EMAIL, mascarar_pii(valor))
    if isinstance(valor, dict):
        return {chave: mascarar_diagnostico(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [mascarar_diagnostico(item) for item in valor]
    return valor


def resumo_do_texto(texto: str, limite: int = 120) -> str:
    linha = " ".join(texto.split())
    return linha if len(linha) <= limite else f"{linha[: limite - 1]}…"


def _avisar_sentry(relato_id: UUID, diagnostico: dict[str, Any] | None) -> None:
    """Aviso sem o texto do usuário: só o id (para achar no CLI), a plataforma e a versão."""
    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover - dependência do projeto
        return
    if not sentry_sdk.is_initialized():
        return
    with sentry_sdk.new_scope() as escopo:
        escopo.set_tag("relato_id", str(relato_id))
        if diagnostico:
            escopo.set_tag("plataforma", str(diagnostico.get("plataforma")))
            escopo.set_tag("versao_app", str(diagnostico.get("versao_app")))
        sentry_sdk.capture_message("Relato de problema recebido", level="info")


def _saida(relato: Relato) -> RelatoSaida:
    return RelatoSaida(
        id=relato.id,
        resumo=resumo_do_texto(relato.texto),
        com_diagnostico=relato.diagnostico is not None,
        criado_em=relato.criado_em,
    )


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def relatar(
    dados: RelatoEntrada, usuario_id: Usuario, sessao: Sessao, redis: RedisDep
) -> RelatoSaida:
    """Guarda o relato (texto e diagnóstico mascarados)."""
    espera = await verificar_limite(redis, f"relatos:{usuario_id}", *LIMITE_RELATOS)
    if espera:
        raise ErroLimite(espera)
    diagnostico = (
        mascarar_diagnostico(dados.diagnostico.model_dump(mode="json"))
        if dados.diagnostico
        else None
    )
    relato = Relato(
        usuario_id=usuario_id, texto=mascarar_pii(dados.texto.strip()), diagnostico=diagnostico
    )
    sessao.add(relato)
    await sessao.flush()
    await sessao.refresh(relato)
    try:
        _avisar_sentry(relato.id, diagnostico)
    except Exception:  # o aviso é um extra; o relato já está guardado
        registro.warning("não consegui avisar o Sentry do relato", exc_info=True)
    registro.info("relato de problema recebido: %s", relato.id)
    return _saida(relato)


@roteador.get("")
async def listar(usuario_id: Usuario, sessao: Sessao) -> list[RelatoSaida]:
    """Os relatos que o usuário mandou, do mais novo para o mais antigo."""
    relatos = await sessao.scalars(
        select(Relato)
        .where(Relato.usuario_id == usuario_id)
        .order_by(Relato.criado_em.desc())
        .limit(MAX_LISTA)
    )
    return [_saida(r) for r in relatos]


@roteador.delete("/{relato_id}", status_code=status.HTTP_204_NO_CONTENT)
async def retirar(relato_id: UUID, usuario_id: Usuario, sessao: Sessao) -> None:
    """Retira (apaga) um relato do próprio usuário."""
    resultado = await sessao.execute(
        delete(Relato).where(Relato.id == relato_id, Relato.usuario_id == usuario_id)
    )
    if not resultado.rowcount:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Relato não encontrado.")
