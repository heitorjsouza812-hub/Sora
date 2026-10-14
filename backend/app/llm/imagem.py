"""Geração de imagem (ferramenta ``gerar_imagem`` do Designer).

Especificação: §4 ("``gerar_imagem`` usa a API de imagem do provedor do usuário pelo LiteLLM
(``image_generation``), com a chave dele") e §5 (papel ``imagem``, capacidade ``imagem``).

Este módulo só gera os bytes. Virar anexo (``origem = especialista``) é da ferramenta, em
``app/ferramentas/``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.llm.provedores import ConfigProvedor

ProporcaoImagem = Literal["1:1", "4:5", "9:16", "16:9"]


class ImagemGerada(BaseModel):
    conteudo: bytes
    tipo_mime: str
    modelo: str
    custo_usd: Decimal


async def gerar_imagens(
    modelo: str,
    provedor: ConfigProvedor,
    descricao: str,
    *,
    proporcao: ProporcaoImagem = "1:1",
    quantidade: int = 1,
) -> list[ImagemGerada]:
    """Gera de 1 a 4 imagens com o modelo de imagem escolhido pelo seletor (papel ``imagem``)."""
    raise NotImplementedError
