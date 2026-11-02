"""Rotas de envio e leitura de anexos; especificação §2."""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.banco import obter_sessao
from app.core.config import obter_configuracao
from app.core.dependencias import usuario_atual
from app.ferramentas.arquivos import CaminhoInseguro, caminho_do_anexo, validar_nome_arquivo
from app.modelos.esquemas import AnexoSaida
from app.modelos.tabelas import Anexo

roteador = APIRouter(prefix="/anexos", tags=["anexos"], dependencies=[Depends(usuario_atual)])

Sessao = Annotated[AsyncSession, Depends(obter_sessao, scope="function")]
Usuario = Annotated[UUID, Depends(usuario_atual)]

MAX_BYTES = 20 * 1024 * 1024
_BLOCO = 1024 * 1024
_ASSINATURAS: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
}
_TEXTO = frozenset({".txt", ".md", ".csv", ".json"})
_IMAGENS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
EXTENSOES = frozenset(_ASSINATURAS) | _TEXTO


def _tipo(extensao: str) -> str:
    return mimetypes.types_map.get(extensao) or "application/octet-stream"


def _conteudo_confere(extensao: str, dados: bytes) -> bool:
    if extensao in _TEXTO:
        try:
            dados.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    if not dados.startswith(_ASSINATURAS[extensao]):
        return False
    return extensao != ".webp" or dados[8:12] == b"WEBP"


@roteador.post("", status_code=status.HTTP_201_CREATED)
async def enviar_anexo(arquivo: UploadFile, usuario_id: Usuario, sessao: Sessao) -> AnexoSaida:
    """Armazena um arquivo validado de até 20 MB; o tipo vem da extensão e do conteúdo."""
    nome = Path(arquivo.filename or "").name
    try:
        validar_nome_arquivo(nome)
    except CaminhoInseguro as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(erro)) from None
    extensao = Path(nome).suffix.lower()
    if extensao not in EXTENSOES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Tipo de arquivo não aceito.")
    buffer = bytearray()
    while bloco := await arquivo.read(_BLOCO):
        buffer += bloco
        if len(buffer) > MAX_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "O arquivo passa de 20 MB.")
    dados = bytes(buffer)
    if not dados:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "O arquivo está vazio.")
    if not _conteudo_confere(extensao, dados):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "O conteúdo não confere com a extensão."
        )

    anexo_id = uuid4()
    relativo = f"{usuario_id}/{anexo_id}"
    destino = obter_configuracao().pasta_arquivos / relativo

    def gravar() -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(dados)

    await asyncio.to_thread(gravar)
    tipo = _tipo(extensao)
    sessao.add(
        Anexo(
            id=anexo_id,
            usuario_id=usuario_id,
            nome=nome,
            tipo=tipo,
            tamanho=len(dados),
            caminho=relativo,
            origem="usuario",
        )
    )
    try:
        await sessao.commit()
    except Exception:
        await asyncio.to_thread(destino.unlink, True)
        raise
    return AnexoSaida(anexo_id=anexo_id, nome=nome, tipo=tipo, tamanho=len(dados))


@roteador.get("/{anexo_id}", response_class=FileResponse)
async def baixar_anexo(anexo_id: UUID, usuario_id: Usuario, sessao: Sessao) -> FileResponse:
    """Entrega um arquivo pertencente ao usuário autenticado."""
    anexo = await sessao.scalar(
        select(Anexo).where(Anexo.id == anexo_id, Anexo.usuario_id == usuario_id)
    )
    if anexo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo não encontrado.")
    try:
        caminho = caminho_do_anexo(obter_configuracao().pasta_arquivos, anexo.caminho)
    except CaminhoInseguro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo não encontrado.") from None
    if not caminho.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo não encontrado.")
    return FileResponse(
        caminho,
        media_type=anexo.tipo,
        filename=anexo.nome,
        content_disposition_type=(
            "inline" if Path(anexo.nome).suffix.lower() in _IMAGENS else "attachment"
        ),
        headers={"X-Content-Type-Options": "nosniff"},
    )
