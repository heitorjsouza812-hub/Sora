# ruff: noqa: F811
"""Vela-8: aprovações e sessão do PC com Postgres, Redis e a API reais.

- Prumo A2 / Cerca M3: "Sempre permitir" só onde a regra fica presa a algo concreto; o resto é
  recusado com 422 e o cartão segue pendente; a lista "Precisa de você" só oferece a opção
  quando ela vale (o mesmo conjunto no chat e na central).
- Cerca A2: com um bot no controle do PC (vez presa e sem pausa), nenhuma sessão decide cartões:
  a Sora web aberta no navegador do PC recebe 409. Pausado ou com a vez solta, decide.
- Cerca B3: a sessão do PC exige o token de renovação de uma sessão de login do desktop e morre
  com ela.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select

from app.api.aprovacoes import SOB_CONTROLE
from app.computador.pc_usuario_canal import AgentePc, CanalPc
from app.modelos.enumeracoes import StatusAprovacao
from app.modelos.tabelas import Aprovacao, RegraPermissao
from app.revisor.decisoes import SO_UMA_VEZ
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_computador_pc import DESKTOP, entrar_desktop
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


async def _cartao(mundo: Mundo, usuario_id: UUID, agente_id: UUID | None, acao: dict) -> UUID:
    async with mundo.fabrica() as sessao:
        cartao = Aprovacao(
            usuario_id=usuario_id,
            etapa_id=None,
            agente_id=agente_id,
            grupo_id=None,
            acao=acao,
            avaliacao={"dano": "baixo"},
            status=StatusAprovacao.PENDENTE,
            expira_em=datetime.now(UTC) + timedelta(minutes=10),
        )
        sessao.add(cartao)
        await sessao.commit()
        return cartao.id


async def _regras(mundo: Mundo, usuario_id: UUID) -> list[tuple[str, dict[str, Any]]]:
    async with mundo.fabrica() as sessao:
        regras = await sessao.scalars(
            select(RegraPermissao).where(RegraPermissao.usuario_id == usuario_id)
        )
        return [(r.ferramenta, r.condicao) for r in regras]


async def _status(mundo: Mundo, aprovacao_id: UUID) -> str:
    async with mundo.fabrica() as sessao:
        cartao = await sessao.get(Aprovacao, aprovacao_id)
        assert cartao is not None
        return cartao.status.value


async def _conta(cliente: httpx.AsyncClient, mundo: Mundo, email: str) -> tuple[dict, UUID, UUID]:
    from app.modelos.tabelas import Usuario

    auth = await entrar(cliente, mundo.fabrica, email)
    bot = (await cliente.post("/v1/agentes", json={"descricao": "Organiza"}, headers=auth)).json()
    async with mundo.fabrica() as sessao:
        dono = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
    assert dono is not None
    return auth, dono, UUID(bot["id"])


async def test_sempre_permitir_so_onde_a_regra_fica_presa(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth, uid, bot = await _conta(cliente, mundo, "vela8-sempre@exemplo.com")

        async def decidir(aprovacao_id: UUID, decisao: str) -> httpx.Response:
            return await cliente.post(
                f"/v1/aprovacoes/{aprovacao_id}/decidir", json={"decisao": decisao}, headers=auth
            )

        # Prumo A2: o bot mudando as próprias instruções nunca vira regra
        instrucoes = await _cartao(
            mundo, uid, bot, {"ferramenta": "propor_instrucoes", "argumentos": {"texto": "x"}}
        )
        recusado = await decidir(instrucoes, "sempre_permitir")
        assert recusado.status_code == 422 and recusado.json()["detail"] == SO_UMA_VEZ
        assert await _status(mundo, instrucoes) == "pendente"
        recusados = [
            {"ferramenta": "mcp__gmail__send_message", "condicao": {"para": "a@b.c"}},
            {"ferramenta": "computador_agir", "argumentos": {"alvo": "pc_usuario"}},
            {"ferramenta": "executar_comando", "argumentos": {"comando": "ls"}},
        ]
        for acao in recusados:
            cartao = await _cartao(mundo, uid, bot, acao)
            assert (await decidir(cartao, "sempre_permitir")).status_code == 422, acao

        # a lista "Precisa de você" só oferece "Sempre permitir" onde ele vale
        virtual = await _cartao(
            mundo, uid, bot, {"ferramenta": "computador_agir", "argumentos": {"acoes": []}}
        )
        lista = (await cliente.get("/v1/atencao", headers=auth)).json()
        valores = {p["id"]: [o["valor"] for o in p["opcoes"]] for p in lista}
        assert valores[str(instrucoes)] == ["permitir", "negar"]
        assert valores[str(virtual)] == ["permitir", "sempre_permitir", "negar"]

        # Cerca M3: "sempre" no computador virtual fica preso ao alvo, nunca condição vazia
        assert (await decidir(virtual, "sempre_permitir")).status_code == 204
        assert await _regras(mundo, uid) == [("computador_agir", {"alvo": "virtual"})]

        # "uma vez" e "recusar" continuam valendo para tudo
        assert (await decidir(instrucoes, "permitir")).status_code == 204
        assert await _regras(mundo, uid) == [("computador_agir", {"alvo": "virtual"})]

        # domínio novo: o botão antigo manda "sempre_permitir"; vale como uma vez, sem regra
        dominio = await _cartao(
            mundo,
            uid,
            bot,
            {"tipo": "aprovar_dominio", "ferramenta": "navegador_abrir", "dominio": "x.com"},
        )
        async with mundo.fabrica() as sessao:
            cartao = await sessao.get(Aprovacao, dominio)
            assert cartao is not None
            cartao.acao = {**cartao.acao, "particao": "inexistente"}
            await sessao.commit()
        assert (await decidir(dominio, "sempre_permitir")).status_code == 422  # perfil sumiu
        assert await _regras(mundo, uid) == [("computador_agir", {"alvo": "virtual"})]


async def test_com_bot_no_pc_so_o_app_de_desktop_decide(mundo: Mundo) -> None:
    email = "vela8-pc@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        web, uid, bot = await _conta(cliente, mundo, email)
        desktop, renovacao = await entrar_desktop(cliente, email)
        sessao = await cliente.post(
            "/v1/computador-pc/sessao",
            json={"dispositivo": "PC", "autorizados": [str(bot)], "token_renovacao": renovacao},
            headers=desktop,
        )
        assert sessao.status_code == 200, sessao.text
        pc_sessao = sessao.json()["sessao_id"]
        cartao = await _cartao(
            mundo, uid, bot, {"ferramenta": "mcp__notion__criar_pagina", "condicao": {}}
        )
        url = f"/v1/aprovacoes/{cartao}/decidir"
        redis = Redis.from_url(mundo.url_redis, decode_responses=True)
        try:
            canal = CanalPc(redis)
            await canal.pegar_vez(uid, AgentePc(bot, "Atlas", "#56A8FF"))

            # o bot clicando em "Sempre permitir" na Sora web do navegador do PC: 409
            for cabecalhos in (web, {**web, **DESKTOP}, {**web, "X-Sora-Pc-Sessao": "f" * 32}):
                tentativa = await cliente.post(
                    url, json={"decisao": "sempre_permitir"}, headers=cabecalhos
                )
                assert tentativa.status_code == 409, tentativa.text
                assert tentativa.json()["detail"] == SOB_CONTROLE
            assert await _status(mundo, cartao) == "pendente"
            assert await _regras(mundo, uid) == []

            # bot pausado (o usuário mexeu no PC): o bot não age, qualquer sessão decide
            await canal.marcar_pausado(uid, bot)
            outro = await _cartao(mundo, uid, bot, {"ferramenta": "mcp__x__ler_algo"})
            pausado = await cliente.post(
                f"/v1/aprovacoes/{outro}/decidir", json={"decisao": "negar"}, headers=web
            )
            assert pausado.status_code == 204
            await canal.limpar_pausa(uid, bot)

            # nem o app de desktop decide com a vez presa (nenhum cabeçalho abre exceção);
            # o bot solta a vez quando o cartão dele abre, e daí qualquer sessão decide
            pelo_app = await cliente.post(
                url,
                json={"decisao": "permitir"},
                headers={**desktop, "X-Sora-Pc-Sessao": pc_sessao},
            )
            assert pelo_app.status_code == 409, pelo_app.text
            await canal.soltar_vez(uid)
            assert (
                await cliente.post(url, json={"decisao": "permitir"}, headers=desktop)
            ).status_code == 204
        finally:
            await redis.aclose()


async def test_sessao_do_pc_presa_ao_login_do_desktop(mundo: Mundo) -> None:
    email = "vela8-b3@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        web, _uid, bot = await _conta(cliente, mundo, email)
        renovacao_web = cliente.cookies.get("sora_renovacao", path="/v1/auth")
        assert renovacao_web
        await _conta(cliente, mundo, "vela8-b3-b@exemplo.com")
        _, renovacao_de_outra_conta = await entrar_desktop(cliente, "vela8-b3-b@exemplo.com")
        desktop, renovacao = await entrar_desktop(cliente, email)
        rota = "/v1/computador-pc/sessao"
        cabecalho_roubado = {**web, **DESKTOP}  # token de acesso + cabeçalho: não basta

        def corpo(token: str | None) -> dict[str, Any]:
            return {"dispositivo": "PC", "autorizados": [str(bot)], "token_renovacao": token}

        for token in (None, "x" * 40, renovacao_web, renovacao_de_outra_conta):
            negado = await cliente.post(rota, json=corpo(token), headers=cabecalho_roubado)
            assert negado.status_code == 403, (token, negado.text)

        ok = await cliente.post(rota, json=corpo(renovacao), headers=desktop)
        assert ok.status_code == 200, ok.text
        sessao_id = ok.json()["sessao_id"]
        espera = {"sessao_id": sessao_id, "espera": 0}
        assert (
            await cliente.get("/v1/computador-pc/comandos", params=espera, headers=desktop)
        ).status_code == 204

        # Sair no app de desktop: a sessão do PC morre junto
        sair = await cliente.post(
            "/v1/auth/sair", json={"token_renovacao": renovacao}, headers=DESKTOP
        )
        assert sair.status_code == 204
        depois = await cliente.get("/v1/computador-pc/comandos", params=espera, headers=desktop)
        # O token de acesso do desktop morre junto com a sessão (antes valia até vencer e a
        # rota respondia 409 por a sessão do PC ter caído); o estado abaixo confere o PC.
        assert depois.status_code == 401
        estado = (await cliente.get("/v1/computador-pc/estado", headers=web)).json()
        assert estado["conectado"] is False
