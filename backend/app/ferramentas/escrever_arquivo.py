"""Ferramenta ``escrever_arquivo`` (especificação §4). Escreve só na pasta da
cadeia; o arquivo vira anexo com ``origem = especialista``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.ferramentas.base import ContextoFerramenta


class EscreverArquivo(BaseModel):
    """Salva um texto longo num arquivo da cadeia."""

    nome: str = Field(min_length=1, max_length=120, description="Nome do arquivo, sem pastas")
    conteudo: str


async def escrever_arquivo(args: EscreverArquivo, contexto: ContextoFerramenta) -> str:
    """Grava o arquivo, cria o anexo e devolve o ``anexo_id``."""
    raise NotImplementedError
