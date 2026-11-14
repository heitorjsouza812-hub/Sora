# ruff: noqa: F811
"""Rotas do navegador do bot ao vivo (Farol-2, item 18) com Postgres, Redis e a API reais.

"Estou assistindo", a última captura com controle de dono e os pedidos do usuário (clicar,
digitar, tecla, rolar) na aba assumida. O worker e o Chromium estão em
``tests/unitarios/test_farol2_navegador_ao_vivo.py``; aqui o que importa é a porta de entrada:
dono, aba assumida, validação e que o texto digitado não fica em lugar nenhum.
"""

from __future__ import annotations

import base64
import json
import logging
from uuid import uuid4

import httpx
import pytest
from redis.asyncio import Redis

from app.navegador.ao_vivo import (
    CHAVE_ASSISTINDO,
    CHAVE_ASSUMIDA,
    CHAVE_CAPTURA,
    CHAVE_DONO,
    FILA_COMANDOS,
    MAX_FILA,
)
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao

JPEG = b"\xff\xd8\xff\xe0falso-jpeg"
SEGREDO = "S3nh@-Muito-Secreta-9"


def _usuario_do_token(cabecalhos: dict) -> str:
    payload = cabecalhos["Authorization"].split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["sub"]


async def test_assistir_captura_e_pedidos_so_para_o_dono(
    mundo: Mundo, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    redis = Redis.from_url(mundo.url_redis, decode_responses=True)
    aba = uuid4()
    try:
        async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
            a = await entrar(cliente, mundo.fabrica, "ao-vivo-a@exemplo.com")
            b = await entrar(cliente, mundo.fabrica, "ao-vivo-b@exemplo.com")
            bot = (
                await cliente.post(
                    "/v1/agentes", json={"descricao": "Pesquisa preços de café"}, headers=a
                )
            ).json()

            # estou assistindo: liga por 12 s; só o dono do bot
            assistir = f"/v1/agentes/{bot['id']}/navegador/assistir"
            ok = await cliente.post(assistir, headers=a)
            assert ok.status_code == 200 and ok.json() == {"expira_em_segundos": 12}
            assert 0 < await redis.ttl(CHAVE_ASSISTINDO.format(agente_id=bot["id"])) <= 12
            assert (await cliente.post(assistir, headers=b)).status_code == 404
            assert (await cliente.post(assistir)).status_code == 401

            # captura: sem quadro ainda = 404; com quadro, só o dono (JPEG, sem cache)
            captura = f"/v1/navegador/abas/{aba}/captura"
            assert (await cliente.get(captura, headers=a)).status_code == 404
            await redis.set(CHAVE_CAPTURA.format(aba_id=aba), base64.b64encode(JPEG).decode())
            await redis.set(CHAVE_DONO.format(aba_id=aba), _usuario_do_token(a))
            vista = await cliente.get(captura, headers=a)
            assert vista.status_code == 200 and vista.content == JPEG
            assert vista.headers["content-type"] == "image/jpeg"
            assert vista.headers["cache-control"] == "no-store"
            assert (await cliente.get(captura, headers=b)).status_code == 404  # aba da outra conta
            assert (await cliente.get(captura)).status_code == 401

            # pedidos: só com a aba assumida
            clique = {"x": 100, "y": 65, "largura": 640, "altura": 360}
            base = f"/v1/navegador/abas/{aba}"
            assert (await cliente.post(f"{base}/clicar", json=clique, headers=a)).status_code == 409
            await redis.set(CHAVE_ASSUMIDA.format(aba_id=aba), "1")
            enviado = await cliente.post(f"{base}/clicar", json=clique, headers=a)
            assert enviado.status_code == 202 and enviado.json() == {"enviado": True}
            fila = FILA_COMANDOS.format(aba_id=aba)
            (item,) = await redis.lrange(fila, 0, -1)
            assert json.loads(item) | {"usuario_id": None} == {
                "tipo": "clicar",
                "usuario_id": None,
                "x": 100,
                "y": 65,
                "largura": 640,
                "altura": 360,
                "texto": None,
                "tecla": None,
                "dy": None,
            }
            assert 0 < await redis.ttl(fila) <= 30  # pedido que ninguém executou expira
            await redis.delete(fila)

            # texto, tecla e rolagem; e a outra conta continua de fora
            assert (
                await cliente.post(f"{base}/digitar", json={"texto": SEGREDO}, headers=a)
            ).status_code == 202
            assert (
                await cliente.post(f"{base}/tecla", json={"tecla": "Enter"}, headers=a)
            ).status_code == 202
            assert (
                await cliente.post(f"{base}/rolar", json={"dy": -300}, headers=a)
            ).status_code == 202
            assert await redis.llen(fila) == 3
            for rota, corpo in (
                ("clicar", clique),
                ("digitar", {"texto": "x"}),
                ("tecla", {"tecla": "Enter"}),
                ("rolar", {"dy": 10}),
            ):
                resposta = await cliente.post(f"{base}/{rota}", json=corpo, headers=b)
                assert resposta.status_code == 404, rota
                assert (await cliente.post(f"{base}/{rota}", json=corpo)).status_code == 401

            # validação
            for rota, corpo in (
                ("clicar", {**clique, "x": 640}),  # fora da imagem
                ("clicar", {"x": 1, "y": 1}),
                ("digitar", {"texto": ""}),
                ("digitar", {"texto": "a" * 501}),
                ("tecla", {"tecla": "Control+w"}),
                ("rolar", {"dy": 0}),
                ("rolar", {"dy": 99_999}),
            ):
                resposta = await cliente.post(f"{base}/{rota}", json=corpo, headers=a)
                assert resposta.status_code == 422, (rota, corpo, resposta.text)

            # a fila tem teto: ninguém empilha pedidos sem fim
            for _ in range(MAX_FILA):
                await redis.rpush(fila, "{}")
            cheio = await cliente.post(f"{base}/rolar", json={"dy": 5}, headers=a)
            assert cheio.status_code == 429

        # o texto digitado não foi parar em log nenhum
        assert SEGREDO not in " ".join(r.getMessage() for r in caplog.records)
    finally:
        for chave in (CHAVE_CAPTURA, CHAVE_DONO, CHAVE_ASSUMIDA):
            await redis.delete(chave.format(aba_id=aba))
        await redis.delete(FILA_COMANDOS.format(aba_id=aba))
        await redis.aclose()


async def test_arquivo_do_computador_vira_anexo_baixavel_so_pelo_dono(mundo: Mundo) -> None:
    """``computador_entregar_arquivo``: o anexo real (disco + banco) sai por ``GET /v1/anexos``."""
    from app.computador.ferramentas import guardar_anexo_do_computador
    from app.ferramentas import saidas_do_turno
    from app.ferramentas.base import ContextoFerramenta

    saidas_do_turno.limpar()
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        a = await entrar(cliente, mundo.fabrica, "ao-vivo-c@exemplo.com")
        b = await entrar(cliente, mundo.fabrica, "ao-vivo-d@exemplo.com")
        from uuid import UUID

        usuario, agente = UUID(_usuario_do_token(a)), uuid4()
        ctx = ContextoFerramenta(usuario_id=usuario, agente_id=agente, conversa_id=uuid4())
        dados = "produto;café\nlatte;12\n".encode()
        anexo_id = await guardar_anexo_do_computador(ctx, "maio.csv", dados)

        baixado = await cliente.get(f"/v1/anexos/{anexo_id}", headers=a)
        assert baixado.status_code == 200 and baixado.content == dados
        assert (await cliente.get(f"/v1/anexos/{anexo_id}", headers=b)).status_code == 404
        # a próxima mensagem do bot leva o anexo mesmo que o modelo esqueça o id
        assert saidas_do_turno.recolher(usuario, agente) == [anexo_id]
        # nome estranho vira um nome seguro em vez de derrubar a entrega
        outro = await guardar_anexo_do_computador(ctx, "../../x", b"abc")
        assert (await cliente.get(f"/v1/anexos/{outro}", headers=a)).status_code == 200
