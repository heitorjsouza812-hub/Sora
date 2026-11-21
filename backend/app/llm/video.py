"""Geração de vídeo pelo provedor do usuário (Onda 3, item 17).

Em 2026-11-20 o único caminho com a chave do próprio usuário é o **Gemini Omni Flash** do Google
(``gemini-omni-1.2-flash``), pela Interactions API da Gemini API:

- a OpenAI desligou a API de vídeo (Sora 2) em 2026-09-24, sem substituta;
- o Google desligou o Veo 3.0 (2026-06-30) e o Veo 3.1 de prévia (2026-10-22) na Gemini API e
  indica o Omni Flash no lugar.

Pedido: ``POST https://generativelanguage.googleapis.com/v1beta/interactions`` com
``{"model", "input", "response_format": {"type": "video", "aspect_ratio", "resolution",
"duration"}}``. A resposta é síncrona e traz o MP4 em base64 dentro de ``steps`` (passo
``model_output``, item ``{"type": "video", "mime_type": "video/mp4", "data": …}``).

Preço publicado (camada paga, sem plano grátis): 5.792 tokens por segundo de 720p a US$ 12 por
milhão, ≈ US$ 0,07/s; 360p ≈ US$ 0,023/s; 1080p ≈ US$ 0,104/s. A estimativa do cartão usa isso.

Com ``SORA_MODELO_FALSO=1`` (só dev/teste) não há rede: devolve bytes de marcação, custo zero.
"""

from __future__ import annotations

import base64
from decimal import Decimal
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from app.llm.falso import modelo_falso_ativo
from app.llm.provedores import ConfigProvedor, ErroProvedor
from app.modelos.enumeracoes import TipoProvedor

MODELO_VIDEO = "gemini-omni-1.2-flash"
URL_INTERACOES = "https://generativelanguage.googleapis.com/v1beta/interactions"
PRAZO_SEGUNDOS = 600.0
MAX_BYTES_VIDEO = 150 * 1024 * 1024
DURACAO_MINIMA = 3
DURACAO_MAXIMA = 15

Proporcao = Literal["16:9", "9:16"]
Qualidade = Literal["360p", "720p", "1080p"]

PRECO_POR_SEGUNDO: dict[str, Decimal] = {
    "360p": Decimal("0.023"),
    "720p": Decimal("0.07"),
    "1080p": Decimal("0.104"),
}


class VideoGerado(BaseModel):
    conteudo: bytes
    tipo_mime: str
    modelo: str
    custo_usd: Decimal


def custo_estimado(duracao: int, qualidade: str) -> Decimal:
    return (PRECO_POR_SEGUNDO.get(qualidade, PRECO_POR_SEGUNDO["720p"]) * duracao).quantize(
        Decimal("0.01")
    )


def _video_da_resposta(dados: Any) -> tuple[bytes, str]:
    """Tira o MP4 de ``steps[].content[]`` (passo ``model_output``)."""
    passos = dados.get("steps") if isinstance(dados, dict) else None
    for passo in passos or []:
        if not isinstance(passo, dict) or passo.get("type") != "model_output":
            continue
        conteudo = passo.get("content")
        itens = conteudo if isinstance(conteudo, list) else [conteudo]
        for item in itens:
            if isinstance(item, dict) and item.get("type") == "video" and item.get("data"):
                try:
                    bruto = base64.b64decode(item["data"], validate=False)
                except (ValueError, TypeError) as erro:
                    raise ErroProvedor("O Google devolveu um vídeo ilegível.") from erro
                return bruto, str(item.get("mime_type") or "video/mp4")
    raise ErroProvedor("O Google terminou sem devolver o vídeo. Tente outra descrição.")


def _mensagem_do_erro(resposta: httpx.Response) -> str:
    if resposta.status_code in (401, 403):
        return "A chave do Google não tem acesso à geração de vídeo (precisa da camada paga)."
    if resposta.status_code == 429:
        return "O limite da sua conta do Google para vídeo foi atingido. Tente mais tarde."
    if resposta.status_code == 400:
        try:
            detalhe = str(resposta.json().get("error", {}).get("message", ""))[:200]
        except ValueError:
            detalhe = ""
        return "O Google recusou o pedido de vídeo" + (f": {detalhe}" if detalhe else ".")
    return f"O Google não gerou o vídeo (erro {resposta.status_code}). Tente de novo."


async def gerar_video(
    config: ConfigProvedor,
    descricao: str,
    *,
    proporcao: Proporcao = "16:9",
    duracao: int = 8,
    qualidade: Qualidade = "720p",
    cliente: httpx.AsyncClient | None = None,
) -> VideoGerado:
    if not DURACAO_MINIMA <= duracao <= DURACAO_MAXIMA:
        raise ValueError(f"O vídeo tem de ter de {DURACAO_MINIMA} a {DURACAO_MAXIMA} segundos.")
    if modelo_falso_ativo():
        return VideoGerado(
            conteudo=b"\x00\x00\x00\x18ftypmp42video-falso-sora",
            tipo_mime="video/mp4",
            modelo="falso/video",
            custo_usd=Decimal(0),
        )
    if config.tipo != TipoProvedor.GOOGLE or config.api_key is None:
        raise ErroProvedor("Para gerar vídeo, conecte uma conta do Google (Gemini).")
    corpo = {
        "model": MODELO_VIDEO,
        "input": descricao,
        "response_format": {
            "type": "video",
            "aspect_ratio": proporcao,
            "resolution": qualidade,
            "duration": f"{duracao}s",
        },
    }
    cabecalhos = {
        "x-goog-api-key": config.api_key.get_secret_value(),
        "Content-Type": "application/json",
    }
    proprio = cliente is None
    http = cliente or httpx.AsyncClient(timeout=PRAZO_SEGUNDOS, follow_redirects=False)
    try:
        resposta = await http.post(URL_INTERACOES, json=corpo, headers=cabecalhos)
    except httpx.HTTPError as erro:
        raise ErroProvedor("Não consegui falar com o Google para gerar o vídeo.") from erro
    finally:
        if proprio:
            await http.aclose()
    if resposta.status_code >= 400:
        raise ErroProvedor(_mensagem_do_erro(resposta))
    if len(resposta.content) > MAX_BYTES_VIDEO * 4 // 3 + 4096:
        raise ErroProvedor("O vídeo devolvido passa do tamanho aceito.")
    try:
        dados = resposta.json()
    except ValueError as erro:
        raise ErroProvedor("O Google devolveu uma resposta ilegível.") from erro
    if isinstance(dados, dict) and dados.get("status") == "failed":
        raise ErroProvedor("O Google não conseguiu gerar este vídeo. Tente outra descrição.")
    conteudo, tipo = _video_da_resposta(dados)
    if len(conteudo) > MAX_BYTES_VIDEO:
        raise ErroProvedor("O vídeo devolvido passa do tamanho aceito.")
    return VideoGerado(
        conteudo=conteudo,
        tipo_mime=tipo if tipo.startswith("video/") else "video/mp4",
        modelo=MODELO_VIDEO,
        custo_usd=custo_estimado(duracao, qualidade),
    )
