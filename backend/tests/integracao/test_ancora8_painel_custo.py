"""Âncora-8: custo das chamadas dos agentes, texto das instruções no cartão e passos da
conversa direta no painel Trabalho. Provedor HTTP local (formato OpenAI), worker ARQ real."""

# ruff: noqa: F401, F811
from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select

from app.modelos.enumeracoes import StatusCadeia, StatusEtapa
from app.modelos.tabelas import Aprovacao, Cadeia, ChamadaModelo, Etapa, Passo
from tests.integracao.test_fase_b_pronto import (
    _porta_livre,
    ambiente_fase_b,
    ambiente_fase_b_arq,
    ler_sse,
    servicos_fase_b,
)
from tests.integracao.test_fase_b_robustez import (
    AmbienteHttp,
    _aprovacao_da_sora,
    _cadeia_e_etapa,
    _conversa_com_pedido,
    _enfileirar,
    _entregar_do_provedor,
    ambiente_http,
    completar_ferramenta,
    completar_texto,
    esperar,
    usuario_com_modelo_http,
)

pytestmark = pytest.mark.integracao


async def _chamadas(amb: AmbienteHttp, usuario_id) -> list[ChamadaModelo]:
    async with amb.fabrica() as sessao:
        return list(
            (
                await sessao.scalars(
                    select(ChamadaModelo).where(
                        ChamadaModelo.usuario_id == usuario_id, ChamadaModelo.papel != "sistema1"
                    )
                )
            ).all()
        )


async def test_chamadas_da_sora_entram_no_uso_do_mes(ambiente_http: AmbienteHttp) -> None:
    amb = ambiente_http
    amb.provedor.responder = lambda corpo, n: completar_texto("Oi! Como posso ajudar?")
    async with httpx.AsyncClient(base_url=amb.url_api, timeout=60) as cliente:
        auth, usuario_id = await usuario_com_modelo_http(amb, cliente, "custo-sora@exemplo.com")
        _, mensagem_id = await _conversa_com_pedido(amb, usuario_id, "Oi")
        await _enfileirar(amb.url_redis, "responder_direto", str(mensagem_id))

        async def gravou() -> list[ChamadaModelo]:
            return await _chamadas(amb, usuario_id)

        linhas = await esperar(gravou, "a chamada do agente não foi gravada")
        assert len(linhas) == len(amb.provedor.chamadas) >= 1
        linha = linhas[0]
        assert linha.papel == "sora" and linha.modelo == "openai/modelo-local"
        assert (linha.tokens_entrada, linha.tokens_saida) == (20, 10)
        assert linha.provedor_id is not None and linha.cadeia_id is None
        uso = (await cliente.get("/v1/uso", headers=auth)).json()
        sora = [i for i in uso["itens"] if i["papel"] == "sora"]
        assert sum(i["tokens_entrada"] for i in sora) == 20 * len(linhas)


async def test_chamadas_da_etapa_da_cadeia_entram_no_uso(ambiente_http: AmbienteHttp) -> None:
    amb = ambiente_http
    amb.provedor.responder = lambda corpo, n: _entregar_do_provedor()
    async with httpx.AsyncClient(base_url=amb.url_api, timeout=60) as cliente:
        _, usuario_id = await usuario_com_modelo_http(amb, cliente, "custo-etapa@exemplo.com")
        _, cadeia_id, etapa_id = await _cadeia_e_etapa(
            amb.fabrica, usuario_id, StatusCadeia.EXECUTANDO
        )
        await _enfileirar(amb.url_redis, "executar_etapa", str(etapa_id))

        async def concluida() -> bool:
            async with amb.fabrica() as sessao:
                return (await sessao.get(Etapa, etapa_id)).status == StatusEtapa.CONCLUIDA

        await esperar(concluida, "a etapa não concluiu")
        linhas = await _chamadas(amb, usuario_id)
        assert linhas, "a chamada do especialista não foi gravada"
        assert {linha.cadeia_id for linha in linhas} == {cadeia_id}
        assert {linha.etapa_id for linha in linhas} == {etapa_id}
        assert all(linha.tokens_entrada == 20 and linha.provedor_id for linha in linhas)


async def test_conversa_direta_publica_prompt_e_passos_sem_gravar_no_banco(
    ambiente_http: AmbienteHttp,
) -> None:
    """Item 5: o painel Trabalho recebe o pedido e a ferramenta (rótulo e resultado), com o
    mesmo evento ``passo`` da cadeia, e a fala não vira passo."""
    amb = ambiente_http

    def roteiro(corpo, n):
        if n == 1:
            return completar_ferramenta("buscar_memoria", {"consulta": "café"})
        return completar_ferramenta("falar", {"texto": "Não achei nada guardado."})

    amb.provedor.responder = roteiro
    async with httpx.AsyncClient(base_url=amb.url_api, timeout=60) as cliente:
        auth, usuario_id = await usuario_com_modelo_http(amb, cliente, "passos-direta@exemplo.com")
        conversa_id, mensagem_id = await _conversa_com_pedido(
            amb, usuario_id, "O que sabe do café?"
        )
        await _enfileirar(amb.url_redis, "responder_direto", str(mensagem_id))
        eventos = await ler_sse(
            cliente, str(conversa_id), auth, ate=lambda nome, d: nome == "sugestoes"
        )
    passos = [d for nome, d in eventos if nome == "passo"]
    prompt = [p for p in passos if p["tipo"] == "prompt"]
    assert len(prompt) == 1 and prompt[0]["texto"] == "O que sabe do café?"
    assert prompt[0]["origem"] == "usuario" and prompt[0]["status"] == "concluido"
    memoria = [p for p in passos if p.get("ferramenta") == "buscar_memoria"]
    assert [p["status"] for p in memoria] == ["executando", "concluido"]
    assert memoria[0]["passo_id"] == memoria[1]["passo_id"]
    assert memoria[0]["texto"] and memoria[0]["parametros"] == {"consulta": "café"}
    assert memoria[1]["resultado"] is not None
    assert not [p for p in passos if p.get("ferramenta") == "falar"]
    # um id de turno só, que não é de nenhuma etapa
    assert len({p["etapa_id"] for p in passos}) == 1
    turno = UUID(passos[0]["etapa_id"])
    async with amb.fabrica() as sessao:
        assert (
            await sessao.scalar(
                select(func.count()).select_from(Passo).where(Passo.etapa_id == turno)
            )
            == 0
        )
        assert (
            await sessao.scalar(select(func.count()).select_from(Etapa).where(Etapa.id == turno))
            == 0
        )


async def test_cartao_de_instrucoes_leva_o_texto_novo_no_evento_e_na_atencao(
    ambiente_http: AmbienteHttp,
) -> None:
    """Item 4: ``proposta`` no ``aprovacao.pedida`` e em ``GET /v1/atencao``."""
    amb = ambiente_http
    async with httpx.AsyncClient(base_url=amb.url_api, timeout=60) as cliente:
        auth, usuario_id = await usuario_com_modelo_http(amb, cliente, "proposta@exemplo.com")
        cartao = await _aprovacao_da_sora(amb, usuario_id)
        eventos = await ler_sse(
            cliente,
            cartao.acao["conversa_id"],
            auth,
            ate=lambda nome, d: nome == "aprovacao.pedida",
        )
        pedida = next(d for nome, d in eventos if nome == "aprovacao.pedida")
        assert pedida["proposta"]["instrucoes"] == "Responder em tom formal."
        assert pedida["proposta"]["motivo"] == "Pedido do usuário."
        assert "+Responder em tom formal." in pedida["proposta"]["diferenca"]
        itens = (await cliente.get("/v1/atencao", headers=auth)).json()
        item = next(i for i in itens if i["id"] == str(cartao.id))
        assert item["proposta"] == pedida["proposta"]
