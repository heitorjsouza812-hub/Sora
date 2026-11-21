"""Geração de vídeo (Onda 3, item 17): cliente do Gemini Omni Flash e o cartão com o custo."""

from __future__ import annotations

import base64
import json
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from app.ferramentas.gerar_video import GerarVideo, texto_do_custo
from app.llm import video
from app.llm.provedores import ConfigProvedor, ErroProvedor
from app.modelos.enumeracoes import TipoProvedor
from app.revisor.politica import Politica, pode_sem_supervisao, politica_da_ferramenta

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"x" * 64
GOOGLE = ConfigProvedor(tipo=TipoProvedor.GOOGLE, api_key=SecretStr("chave-google-teste"))


@pytest.fixture(autouse=True)
def _sem_modelo_falso(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SORA_MODELO_FALSO", raising=False)
    monkeypatch.setattr(video, "modelo_falso_ativo", lambda: False)


def _cliente(responder) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(transport=httpx.MockTransport(responder))


def _resposta_ok() -> dict:
    return {
        "id": "int-1",
        "object": "interaction",
        "status": "completed",
        "model": video.MODELO_VIDEO,
        "steps": [
            {"type": "thought", "content": [{"type": "text", "text": "..."}]},
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "video",
                        "mime_type": "video/mp4",
                        "data": base64.b64encode(MP4).decode(),
                    }
                ],
            },
        ],
    }


async def test_pede_o_video_no_formato_da_api_e_le_o_mp4() -> None:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(200, json=_resposta_ok())

    async with _cliente(responder) as cliente:
        gerado = await video.gerar_video(
            GOOGLE, "Café sendo servido", proporcao="9:16", duracao=6, cliente=cliente
        )
    assert gerado.conteudo == MP4 and gerado.tipo_mime == "video/mp4"
    assert gerado.modelo == "gemini-omni-1.2-flash"
    assert gerado.custo_usd == Decimal("0.42")  # 6 s x US$ 0,07 (720p)
    [pedido] = pedidos
    assert str(pedido.url) == video.URL_INTERACOES  # a chave nunca vai no endereço
    assert pedido.headers["x-goog-api-key"] == "chave-google-teste"
    assert json.loads(pedido.content) == {
        "model": "gemini-omni-1.2-flash",
        "input": "Café sendo servido",
        "response_format": {
            "type": "video",
            "aspect_ratio": "9:16",
            "resolution": "720p",
            "duration": "6s",
        },
    }


@pytest.mark.parametrize(
    ("codigo", "corpo", "trecho"),
    [
        (403, {}, "camada paga"),
        (429, {}, "limite"),
        (400, {"error": {"message": "prompt bloqueado"}}, "prompt bloqueado"),
        (500, {}, "erro 500"),
    ],
)
async def test_erros_do_google_viram_texto_claro(codigo: int, corpo: dict, trecho: str) -> None:
    async with _cliente(lambda _p: httpx.Response(codigo, json=corpo)) as cliente:
        with pytest.raises(ErroProvedor, match=trecho):
            await video.gerar_video(GOOGLE, "x", cliente=cliente)


async def test_sem_video_na_resposta_ou_falha() -> None:
    sem_video = {"status": "completed", "steps": [{"type": "model_output", "content": []}]}
    async with _cliente(lambda _p: httpx.Response(200, json=sem_video)) as cliente:
        with pytest.raises(ErroProvedor, match="sem devolver o vídeo"):
            await video.gerar_video(GOOGLE, "x", cliente=cliente)
    async with _cliente(lambda _p: httpx.Response(200, json={"status": "failed"})) as cliente:
        with pytest.raises(ErroProvedor, match="não conseguiu"):
            await video.gerar_video(GOOGLE, "x", cliente=cliente)


async def test_precisa_de_conta_do_google_e_duracao_valida() -> None:
    openai = ConfigProvedor(tipo=TipoProvedor.OPENAI, api_key=SecretStr("k"))
    with pytest.raises(ErroProvedor, match="conta do Google"):
        await video.gerar_video(openai, "x")
    with pytest.raises(ValueError, match="de 3 a 15"):
        await video.gerar_video(GOOGLE, "x", duracao=20)


def test_custo_e_cartao() -> None:
    assert video.custo_estimado(10, "720p") == Decimal("0.70")
    assert video.custo_estimado(15, "1080p") == Decimal("1.56")
    assert video.custo_estimado(8, "360p") == Decimal("0.18")
    assert texto_do_custo({"duracao": 8, "qualidade": "720p"}) == (
        "Cobra na sua conta do Google: cerca de US$ 0,56 (8 s em 720p)."
    )
    assert GerarVideo(descricao="x").duracao == 8
    with pytest.raises(ValueError):
        GerarVideo(descricao="x", duracao=16)


def test_video_sempre_pede_aprovacao_e_nunca_roda_em_rotina() -> None:
    assert politica_da_ferramenta("gerar_video") is Politica.CARTAO_FIXO
    assert not pode_sem_supervisao("gerar_video")
