"""Ferramenta ``escrever_arquivo`` (especificação §4). Escreve só na pasta da
cadeia; o arquivo vira anexo com ``origem = especialista``.

O ``nome`` vem do modelo, então é tratado como dado não confiável: o
validador recusa pastas, ``..``, NUL, nomes reservados do Windows e nomes
começando com ponto, e a gravação confere o caminho resolvido
(``app.ferramentas.arquivos``).

Agente individual não tem cadeia: a pasta usa o id da conversa no lugar.
"""

from __future__ import annotations

import asyncio
import mimetypes

from pydantic import BaseModel, Field, field_validator

from app.ferramentas.arquivos import (
    MAX_NOME,
    CaminhoInseguro,
    gravar_na_cadeia,
    validar_nome_arquivo,
)
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.infra import abrir_sessao, raiz_dos_arquivos
from app.modelos.tabelas import Anexo

MAX_CONTEUDO = 1_000_000
"""Caracteres. Acima disso o modelo deve dividir o texto em arquivos."""


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


def tipo_do_arquivo(nome: str) -> str:
    tipo, _ = mimetypes.guess_type(nome)
    return tipo or "text/plain"


async def escrever_arquivo(args: EscreverArquivo, contexto: ContextoFerramenta) -> str:
    """Grava o arquivo (``gravar_na_cadeia``), cria o anexo e devolve o ``anexo_id``."""
    if len(args.conteudo) > MAX_CONTEUDO:
        raise ErroFerramenta("O texto é grande demais. Divida em mais de um arquivo.")
    raiz = raiz_dos_arquivos()
    pasta_id = contexto.cadeia_id or contexto.conversa_id
    try:
        caminho = await asyncio.to_thread(
            gravar_na_cadeia, raiz, contexto.usuario_id, pasta_id, args.nome, args.conteudo
        )
    except (CaminhoInseguro, OSError) as erro:
        raise ErroFerramenta(f"Não consegui gravar o arquivo: {erro}") from erro

    relativo = caminho.relative_to(raiz.resolve()).as_posix()
    anexo = Anexo(
        usuario_id=contexto.usuario_id,
        nome=args.nome,
        tipo=tipo_do_arquivo(args.nome),
        tamanho=caminho.stat().st_size,
        caminho=relativo,
        origem="especialista",
    )
    async with abrir_sessao() as sessao:
        sessao.add(anexo)
        await sessao.flush()
        anexo_id = anexo.id
    return f"Arquivo {args.nome} salvo. anexo_id: {anexo_id}"
