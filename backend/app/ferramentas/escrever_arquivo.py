"""Ferramenta ``escrever_arquivo`` (especificação §4). Escreve só na pasta da
cadeia; o arquivo vira anexo com ``origem = especialista``.

O ``nome`` vem do modelo, então é tratado como dado não confiável: o
validador recusa pastas, ``..``, NUL, nomes reservados do Windows e nomes
começando com ponto, e a gravação confere o caminho resolvido
(``app.ferramentas.arquivos``).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.ferramentas.arquivos import MAX_NOME, validar_nome_arquivo
from app.ferramentas.base import ContextoFerramenta


class EscreverArquivo(BaseModel):
    """Salva um texto longo num arquivo da cadeia."""

    nome: str = Field(
        min_length=1,
        max_length=MAX_NOME,
        description='Só o nome do arquivo, sem pastas (ex.: "relatorio.md")',
    )
    conteudo: str

    @field_validator("nome")
    @classmethod
    def _nome_seguro(cls, nome: str) -> str:
        return validar_nome_arquivo(nome)


async def escrever_arquivo(args: EscreverArquivo, contexto: ContextoFerramenta) -> str:
    """Grava o arquivo (``gravar_na_cadeia``), cria o anexo e devolve o ``anexo_id``."""
    raise NotImplementedError
