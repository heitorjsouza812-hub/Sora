"""Ferramenta ``gerar_imagem`` (especificação §4). Usa a API de imagem do provedor
do usuário pelo LiteLLM (``image_generation``); as imagens viram anexos com
``origem = especialista``. Só existe se houver modelo com a capacidade ``imagem``.

O modelo é escolhido pelo seletor (papel ``imagem``) entre os do próprio usuário; o
custo de cada imagem entra em ``chamadas_modelo``.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.ferramentas.arquivos import pasta_da_cadeia
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.infra import abrir_sessao, raiz_dos_arquivos
from app.llm.custo import CustoChamada, gravar_chamada
from app.llm.imagem import gerar_imagens
from app.llm.provedores import ErroProvedor
from app.modelos.tabelas import Anexo
from app.seletor.repositorio import config_do_provedor, contexto_do_usuario
from app.seletor.seletor import escolher_modelos
from app.seletor.tipos import PapelModelo

EXTENSAO = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


class GerarImagem(BaseModel):
    """Gera imagens a partir de uma descrição."""

    descricao: str = Field(min_length=1)
    proporcao: Literal["1:1", "4:5", "9:16", "16:9"] = "1:1"
    quantidade: int = Field(default=1, ge=1, le=4)


def _gravar(destino: Path, conteudo: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)


async def gerar_imagem(args: GerarImagem, contexto: ContextoFerramenta) -> str:
    """Gera as imagens, grava os anexos e devolve os ids."""
    async with abrir_sessao() as sessao:
        seletor = await contexto_do_usuario(sessao, contexto.usuario_id)
        escolha = escolher_modelos(
            seletor, PapelModelo.IMAGEM, dificuldade=1, precisa=set(), tokens_prompt=0
        )
        if not escolha.modelos:
            raise ErroFerramenta("Não há modelo de imagem conectado.")
        candidato = escolha.modelos[0]
        config = await config_do_provedor(sessao, contexto.usuario_id, candidato.provedor.id)

        try:
            imagens = await gerar_imagens(
                candidato.modelo,
                config,
                args.descricao,
                proporcao=args.proporcao,
                quantidade=args.quantidade,
            )
        except (ErroProvedor, ValueError) as erro:
            raise ErroFerramenta(str(erro)) from erro

        raiz = raiz_dos_arquivos().resolve()
        pasta = pasta_da_cadeia(
            raiz, contexto.usuario_id, contexto.cadeia_id or contexto.conversa_id
        )
        ids: list[uuid.UUID] = []
        for imagem in imagens:
            anexo_id = uuid.uuid4()
            nome = f"imagem-{anexo_id.hex[:8]}.{EXTENSAO.get(imagem.tipo_mime, 'png')}"
            destino = pasta / nome
            await asyncio.to_thread(_gravar, destino, imagem.conteudo)
            sessao.add(
                Anexo(
                    id=anexo_id,
                    usuario_id=contexto.usuario_id,
                    nome=nome,
                    tipo=imagem.tipo_mime,
                    tamanho=len(imagem.conteudo),
                    caminho=destino.relative_to(raiz).as_posix(),
                    origem="especialista",
                )
            )
            ids.append(anexo_id)
            await gravar_chamada(
                sessao,
                contexto.usuario_id,
                CustoChamada(
                    provedor_id=config.provedor_id,
                    papel="imagem",
                    modelo=imagem.modelo,
                    nivel="especial",
                    tokens_entrada=0,
                    tokens_saida=0,
                    custo_usd=imagem.custo_usd,
                    latencia_ms=0,
                ),
                cadeia_id=contexto.cadeia_id,
                etapa_id=contexto.etapa_id,
            )
    lista = ", ".join(str(i) for i in ids)
    return f"{len(ids)} imagem(ns) gerada(s). anexo_ids: {lista}"
