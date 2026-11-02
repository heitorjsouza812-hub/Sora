"""Ferramenta ``ler_anexo`` (especificação §4; tabela ``anexos`` em §1). Só lê
anexos do próprio usuário; a cerca ``<dado_externo>`` é posta por ``MiddlewareCerca``.

O modelo não passa caminho nenhum, só o ``anexo_id`` (UUID validado). As travas:
a consulta filtra por ``anexos.usuario_id = contexto.usuario_id`` (anexo de
outro usuário = "não encontrado") e o ``anexos.caminho`` salvo passa por
``app.ferramentas.arquivos.caminho_do_anexo``, que confere o caminho resolvido
dentro do volume de arquivos.
"""

from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select

from app.busca.ler_pagina import MAX_BYTES, extrair_texto_sem_travar
from app.ferramentas.arquivos import CaminhoInseguro, caminho_do_anexo
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.infra import abrir_sessao, raiz_dos_arquivos
from app.modelos.tabelas import Anexo

MAX_LINHAS_PLANILHA = 2_000
TAMANHO_MAXIMO = MAX_BYTES * 4
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TIPO_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TIPOS_TEXTO = {"application/json", "application/xml", "application/x-yaml"}
SUFIXOS_TEXTO = {".md", ".csv", ".txt", ".json", ".yaml", ".yml"}


class LerAnexo(BaseModel):
    """Lê um arquivo enviado pelo usuário ou gerado por um especialista."""

    anexo_id: UUID


def _ler_planilha(conteudo: bytes) -> str:
    from openpyxl import load_workbook

    pasta = load_workbook(BytesIO(conteudo), read_only=True, data_only=True)
    partes: list[str] = []
    try:
        for aba in pasta.worksheets:
            partes.append(f"## {aba.title}")
            for n, linha in enumerate(aba.iter_rows(values_only=True)):
                if n >= MAX_LINHAS_PLANILHA:
                    partes.append(f"(cortado em {MAX_LINHAS_PLANILHA} linhas)")
                    break
                partes.append(" | ".join("" if c is None else str(c) for c in linha))
    finally:
        pasta.close()
    return "\n".join(partes)


def _ler_documento(conteudo: bytes) -> str:
    from docx import Document

    documento = Document(BytesIO(conteudo))
    partes = [p.text for p in documento.paragraphs if p.text.strip()]
    for tabela in documento.tables:
        for linha in tabela.rows:
            partes.append(" | ".join(c.text for c in linha.cells))
    return "\n".join(partes)


def extrair_do_anexo(conteudo: bytes, tipo: str, nome: str) -> str:
    """Texto de planilha, documento Word ou arquivo de texto (PDF vai por outro caminho)."""
    sufixo = Path(nome).suffix.lower()
    if tipo == TIPO_XLSX or sufixo == ".xlsx":
        return _ler_planilha(conteudo)
    if tipo == TIPO_DOCX or sufixo == ".docx":
        return _ler_documento(conteudo)
    if tipo.startswith("text/") or tipo in TIPOS_TEXTO or sufixo in SUFIXOS_TEXTO:
        texto = conteudo.decode("utf-8", errors="replace")
        if sufixo == ".json" or tipo == "application/json":
            try:
                texto = json.dumps(json.loads(texto), ensure_ascii=False, indent=2)
            except ValueError:
                pass
        return texto
    raise ErroFerramenta(f"Não sei ler arquivos do tipo {tipo or sufixo or 'desconhecido'}.")


async def ler_anexo(args: LerAnexo, contexto: ContextoFerramenta) -> str:
    """Lê o anexo (texto, PDF, planilha, documento) e devolve o conteúdo."""
    async with abrir_sessao() as sessao:
        anexo = await sessao.scalar(
            select(Anexo).where(Anexo.id == args.anexo_id, Anexo.usuario_id == contexto.usuario_id)
        )
    if anexo is None:
        raise ErroFerramenta("Anexo não encontrado.")
    if anexo.tipo.startswith("image/"):
        return f"{anexo.nome} é uma imagem ({anexo.tipo}); não consigo ler texto dela aqui."
    if anexo.tamanho > TAMANHO_MAXIMO:
        raise ErroFerramenta("O arquivo é grande demais para ler.")
    try:
        caminho = caminho_do_anexo(raiz_dos_arquivos(), anexo.caminho)
        conteudo = await asyncio.to_thread(caminho.read_bytes)
    except (CaminhoInseguro, OSError) as erro:
        raise ErroFerramenta("Anexo não encontrado.") from erro

    eh_pdf = anexo.tipo == "application/pdf" or anexo.nome.lower().endswith(".pdf")
    try:
        if eh_pdf:
            _, texto = await extrair_texto_sem_travar(conteudo, "application/pdf", anexo.nome)
        else:
            texto = await asyncio.to_thread(extrair_do_anexo, conteudo, anexo.tipo, anexo.nome)
    except ErroFerramenta:
        raise
    except Exception as erro:
        raise ErroFerramenta(f"Não consegui ler {anexo.nome}.") from erro
    return f"Arquivo: {anexo.nome}\n\n{texto}" if texto.strip() else f"{anexo.nome} está vazio."
