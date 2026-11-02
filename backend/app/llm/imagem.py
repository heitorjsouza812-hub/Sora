"""Geração de imagem (ferramenta ``gerar_imagem`` do Designer).

Especificação: §4 ("``gerar_imagem`` usa a API de imagem do provedor do usuário pelo LiteLLM
(``image_generation``), com a chave dele") e §5 (papel ``imagem``, capacidade ``imagem``).

Este módulo só gera os bytes. Virar anexo (``origem = especialista``) é da ferramenta, em
``app/ferramentas/``.

Com ``SORA_MODELO_FALSO=1`` (só dev/teste) não há rede: devolve um PNG liso por imagem, com
custo zero. Se o provedor responder com uma URL em vez de bytes, o download usa o cliente
seguro de ``app.busca.ler_pagina`` (mesma proteção contra SSRF). Quando o provedor tem
``api_base`` escolhida pelo usuário, o domínio é conferido antes da chamada (a conferência do
IP na conexão, que o chat tem, o LiteLLM não permite injetar na geração de imagem).
"""

from __future__ import annotations

import base64
import struct
import zlib
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from app.llm.falso import modelo_falso_ativo
from app.llm.provedores import (
    ClienteLiteLLMProtegido,
    ConfigProvedor,
    ErroProvedor,
    parametros_litellm,
    politica_de_rede,
)

ProporcaoImagem = Literal["1:1", "4:5", "9:16", "16:9"]

TAMANHOS: dict[str, str] = {
    "1:1": "1024x1024",
    "4:5": "1024x1536",
    "9:16": "1024x1536",
    "16:9": "1536x1024",
}
"""Tamanhos aceitos pela API de imagens da OpenAI; o mais próximo de cada proporção."""

PRAZO_SEGUNDOS = 100
MAX_BYTES_IMAGEM = 20 * 1024 * 1024


class ImagemGerada(BaseModel):
    conteudo: bytes
    tipo_mime: str
    modelo: str
    custo_usd: Decimal


def png_liso(largura: int, altura: int, rgb: tuple[int, int, int]) -> bytes:
    """PNG de uma cor só (usado pelo modelo falso)."""

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return (
            struct.pack(">I", len(dados))
            + tipo
            + dados
            + struct.pack(">I", zlib.crc32(tipo + dados))
        )

    linha = b"\x00" + bytes(rgb) * largura
    bruto = zlib.compress(linha * altura)
    cabecalho = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + bloco(b"IHDR", cabecalho)
        + bloco(b"IDAT", bruto)
        + bloco(b"IEND", b"")
    )


def _falsas(modelo: str, quantidade: int) -> list[ImagemGerada]:
    cores = [(86, 168, 255), (172, 128, 255), (70, 232, 168), (226, 236, 255)]
    return [
        ImagemGerada(
            conteudo=png_liso(64, 64, cores[i % len(cores)]),
            tipo_mime="image/png",
            modelo=modelo,
            custo_usd=Decimal(0),
        )
        for i in range(quantidade)
    ]


def _custo(resposta: Any, modelo: str) -> Decimal:
    import litellm

    try:
        return Decimal(str(litellm.completion_cost(completion_response=resposta, model=modelo)))
    except Exception:
        return Decimal(0)


async def _baixar(url: str) -> tuple[bytes, str]:
    from app.busca.ler_pagina import criar_cliente

    async with criar_cliente() as cliente:
        resposta = await cliente.get(url)
        resposta.raise_for_status()
        conteudo = resposta.content
        tipo = resposta.headers.get("content-type", "image/png").split(";")[0].strip()
        return conteudo, tipo


async def gerar_imagens(
    modelo: str,
    provedor: ConfigProvedor,
    descricao: str,
    *,
    proporcao: ProporcaoImagem = "1:1",
    quantidade: int = 1,
) -> list[ImagemGerada]:
    """Gera de 1 a 4 imagens com o modelo de imagem escolhido pelo seletor (papel ``imagem``)."""
    if not 1 <= quantidade <= 4:
        raise ValueError("A quantidade de imagens vai de 1 a 4.")
    if modelo_falso_ativo():
        return _falsas(modelo, quantidade)

    import litellm

    politica = politica_de_rede()
    parametros = parametros_litellm(provedor, politica)
    if "api_base" in parametros and not politica.rede_local:
        await ClienteLiteLLMProtegido().conferir(parametros["api_base"])
    try:
        resposta = await litellm.aimage_generation(
            model=modelo,
            prompt=descricao,
            n=quantidade,
            size=TAMANHOS[proporcao],
            timeout=PRAZO_SEGUNDOS,
            num_retries=0,
            **parametros,
        )
    except Exception as erro:
        # A mensagem do provedor pode citar a chave; só o tipo do erro sai daqui.
        raise ErroProvedor(f"O provedor não gerou a imagem ({type(erro).__name__}).") from erro

    itens = list(getattr(resposta, "data", None) or [])
    custo_cada = _custo(resposta, modelo) / max(len(itens), 1)
    imagens: list[ImagemGerada] = []
    for item in itens:
        b64 = getattr(item, "b64_json", None)
        url = getattr(item, "url", None)
        if b64:
            conteudo, tipo = base64.b64decode(b64), "image/png"
        elif url:
            conteudo, tipo = await _baixar(url)
        else:
            continue
        if len(conteudo) > MAX_BYTES_IMAGEM:
            raise ErroProvedor("A imagem gerada é grande demais.")
        imagens.append(
            ImagemGerada(conteudo=conteudo, tipo_mime=tipo, modelo=modelo, custo_usd=custo_cada)
        )
    if not imagens:
        raise ErroProvedor("O provedor não devolveu imagem.")
    return imagens
