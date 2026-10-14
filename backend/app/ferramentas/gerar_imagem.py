"""Ferramenta ``gerar_imagem`` (especificação §4). Usa a API de imagem do provedor
do usuário pelo LiteLLM (``image_generation``); as imagens viram anexos com
``origem = especialista``. Só existe se houver modelo com a capacidade ``imagem``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.ferramentas.base import ContextoFerramenta


class GerarImagem(BaseModel):
    """Gera imagens a partir de uma descrição."""

    descricao: str = Field(min_length=1)
    proporcao: Literal["1:1", "4:5", "9:16", "16:9"] = "1:1"
    quantidade: int = Field(default=1, ge=1, le=4)


async def gerar_imagem(args: GerarImagem, contexto: ContextoFerramenta) -> str:
    """Gera as imagens, grava os anexos e devolve os ids."""
    raise NotImplementedError
