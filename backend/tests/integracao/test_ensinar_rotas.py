# ruff: noqa: F811
"""Rotas do "Ensinar" (Onda 3, item 14) com Postgres, Redis e a API reais. A gravação com o
Chromium de verdade está em ``tests/unitarios/test_farol2_navegador_ao_vivo.py``."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select

from app.modelos.tabelas import AbaNavegador, Usuario
from app.navegador import ensinar
from app.navegador.ao_vivo import CHAVE_ASSUMIDA
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


async def test_ensinar_so_na_aba_assumida_do_dono_e_devolve_rascunho(mundo: Mundo) -> None:
    redis = Redis.from_url(mundo.url_redis, decode_responses=True)
    try:
        async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
            a = await entrar(cliente, mundo.fabrica, "ensina-a@exemplo.com")
            b = await entrar(cliente, mundo.fabrica, "ensina-b@exemplo.com")
            bot = (
                await cliente.post("/v1/agentes", json={"descricao": "Compra na loja"}, headers=a)
            ).json()
            aba = uuid4()
            async with mundo.fabrica() as sessao:
                usuario = await sessao.scalar(
                    select(Usuario.id).where(Usuario.email == "ensina-a@exemplo.com")
                )
                sessao.add(
                    AbaNavegador(
                        id=aba,
                        usuario_id=usuario,
                        agente_id=bot["id"],
                        particao="agente",
                        url="https://loja.exemplo/inicio",
                    )
                )
                await sessao.commit()
            rota = f"/v1/navegador/abas/{aba}/ensinar"

            # aba de outra conta não existe; sem assumir, não ensina
            assert (await cliente.post(rota, headers=b)).status_code == 404
            assert (await cliente.post(rota, headers=a)).status_code == 409

            await redis.set(CHAVE_ASSUMIDA.format(aba_id=aba), "1")
            ligado = await cliente.post(rota, headers=a)
            assert ligado.status_code == 200, ligado.text
            assert ligado.json() == {
                "gravando": True,
                "passos": ["Abra https://loja.exemplo/inicio"],
            }
            # concluir sem ter feito nada: avisa e continua gravando
            vazio = await cliente.post(f"{rota}/concluir", headers=a, json={"objetivo": "Buscar"})
            assert vazio.status_code == 422

            # o worker anota (aqui direto no Redis, como ele faz)
            await ensinar.gravar(redis, aba, ensinar.Passo(tipo="clicar", alvo="campo “Buscar”"))
            await ensinar.gravar(
                redis,
                aba,
                ensinar.Passo(tipo="digitar", alvo="campo “Buscar”", texto="notebook"),
            )
            visto = (await cliente.get(rota, headers=a)).json()
            assert visto["passos"][1:] == [
                "Clique em campo “Buscar”",
                "Em campo “Buscar”, digite “notebook” (troque pelo valor do pedido, se for outro)",
            ]
            assert (await cliente.get(rota, headers=b)).status_code == 404

            pronto = await cliente.post(
                f"{rota}/concluir", headers=a, json={"objetivo": "Buscar um produto"}
            )
            assert pronto.status_code == 200, pronto.text
            rascunho = pronto.json()
            assert rascunho["nome"] == "Buscar um produto" and rascunho["passos"] == 3
            assert "Site: loja.exemplo." in rascunho["corpo"]
            # nada foi salvo sozinho, e a gravação acabou
            assert (await cliente.get("/v1/habilidades", headers=a)).json() == []
            assert (await cliente.get(rota, headers=a)).json() == {"gravando": False, "passos": []}

            # cancelar apaga o que foi gravado
            await cliente.post(rota, headers=a)
            assert (await cliente.delete(rota, headers=a)).status_code == 204
            assert await redis.exists(ensinar.CHAVE_GRAVACAO.format(aba_id=aba)) == 0
    finally:
        await redis.aclose()
