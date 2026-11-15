"""HTTP, PostgreSQL, Redis e worker ARQ reais; modelo controlado apenas no teste."""

import asyncio
from time import monotonic
from uuid import UUID, uuid4

import httpx
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from redis.asyncio import Redis
from sqlalchemy import select

from app.eventos.streams import canal_conversa
from app.modelos.tabelas import Cadeia, Conversa, Mensagem
from tests.integracao.relogio_base import Mundo, esperar, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


class ModeloControlado(BaseChatModel):
    iniciou: asyncio.Event
    cancelou: asyncio.Event
    lento: bool = True
    busca: bool = False
    pela_ferramenta: bool = False

    @property
    def _llm_type(self):
        return "controlado-integracao"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, *args, **kwargs):
        raise NotImplementedError

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.lento:
            await run_manager.on_llm_new_token("Trecho parcial preservado")
            self.iniciou.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                self.cancelou.set()
                raise
        if self.busca and not any(isinstance(m, ToolMessage) for m in messages):
            msg = AIMessage(
                content="",
                tool_calls=[dict(name="buscar_web", args={"consulta": "Sora"}, id="busca-1")],
            )
        elif self.pela_ferramenta:
            msg = AIMessage(
                content="",
                tool_calls=[dict(name="falar", args={"texto": "Resposta nova [1]."}, id="fala-1")],
            )
        else:
            msg = AIMessage(content="Resposta nova [1].")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def instalar_modelo(monkeypatch, modelo):
    import app.orquestrador.modelos
    import workers.conversa

    original = app.orquestrador.modelos.modelos_do_papel

    async def modelos(sessao, usuario_id, papel, **kwargs):
        if papel in {"sora", "individual", "pesquisador"}:
            return [modelo]
        return await original(sessao, usuario_id, papel, **kwargs)

    monkeypatch.setattr(app.orquestrador.modelos, "modelos_do_papel", modelos)
    monkeypatch.setattr(workers.conversa, "modelo_falso_ativo", lambda: False)


async def mensagens(cliente, auth, conversa):
    resposta = await cliente.get(f"/v1/conversas/{conversa}/mensagens", headers=auth)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


@pytest.mark.parametrize("modo", ["bot", "sora", "cadeia"])
async def test_parar_encerra_em_um_segundo(mundo: Mundo, monkeypatch, modo, record_property):  # noqa: F811
    modelo = ModeloControlado(iniciou=asyncio.Event(), cancelou=asyncio.Event())
    instalar_modelo(monkeypatch, modelo)
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, f"parar-{uuid4()}@exemplo.com")
        outro = await entrar(cliente, mundo.fabrica, f"outro-{uuid4()}@exemplo.com")
        dados = {
            "texto": "oi"
            if modo != "cadeia"
            else "Pesquise o mercado e escreva um relatório completo"
        }
        if modo == "bot":
            bot = await cliente.post(
                "/v1/agentes",
                headers=auth,
                json={
                    "nome": "Pausa",
                    "papel": "individual",
                    "funcao": "Pesquisa",
                    "instrucoes": "Responda em português",
                },
            )
            assert bot.status_code == 201, bot.text
            dados["agente_id"] = bot.json()["id"]
        criada = await cliente.post("/v1/conversas", headers=auth, json=dados)
        assert criada.status_code == 201, criada.text
        conversa = criada.json()["id"]
        await mundo.iniciar_worker()
        await asyncio.wait_for(modelo.iniciou.wait(), 30)
        rota = f"/v1/conversas/{conversa}/parar"
        assert (await cliente.post(rota, headers=outro)).status_code == 404
        assert not modelo.cancelou.is_set()
        inicio = monotonic()
        assert (await cliente.post(rota, headers=auth)).status_code == 202
        await asyncio.wait_for(modelo.cancelou.wait(), 1)

        async def interrompida():
            return [
                m
                for m in await mensagens(cliente, auth, conversa)
                if m["autor"] != "usuario" and m["estado"] == "interrompida"
            ]

        parcial = await esperar(interrompida, limite_s=1)
        assert monotonic() - inicio < 1
        record_property("parada_ms", round((monotonic() - inicio) * 1000, 1))
        assert parcial[0]["conteudo"] == "Trecho parcial preservado"
        assert (await cliente.post(rota, headers=auth)).status_code == 202
        await asyncio.sleep(0.2)
        assert len(await interrompida()) == 1
        async with mundo.fabrica() as sessao:
            pedido = await sessao.get(Mensagem, UUID(parcial[0]["id"]))
            conversa_bd = await sessao.get(Conversa, UUID(conversa))
            assert conversa_bd is not None
            if modo == "cadeia":
                cadeia = await sessao.scalar(
                    select(Cadeia).where(Cadeia.conversa_id == UUID(conversa))
                )
                assert cadeia.status.value == "cancelada"
            assert pedido.estado == "interrompida"
        redis = Redis.from_url(mundo.url_redis)
        try:
            eventos = await redis.xrange(canal_conversa(UUID(conversa)))
            assert any(
                b'"interrompida"' in campos.get(b"dados", b"")
                or b'"interrompida"' in campos.get(b"data", b"")
                for _, campos in eventos
            ), eventos[-3:]
        finally:
            await redis.aclose()


async def test_editar_refazer_avaliar_e_isolar(mundo: Mundo):  # noqa: F811
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, f"edicao-{uuid4()}@exemplo.com")
        outro = await entrar(cliente, mundo.fabrica, f"intruso-{uuid4()}@exemplo.com")
        bot = (
            await cliente.post(
                "/v1/agentes",
                headers=auth,
                json={
                    "nome": "Texto",
                    "papel": "individual",
                    "funcao": "Escrita",
                    "instrucoes": "Responda",
                },
            )
        ).json()
        criada = await cliente.post(
            "/v1/conversas", headers=auth, json={"texto": "oi", "agente_id": bot["id"]}
        )
        conversa = criada.json()["id"]
        await mundo.iniciar_worker()

        async def resposta():
            return [m for m in await mensagens(cliente, auth, conversa) if m["autor"] != "usuario"]

        antiga = (await esperar(resposta))[-1]
        base = f"/v1/conversas/{conversa}/mensagens"
        for valor in (1, -1, None):
            avaliada = await cliente.put(
                f"{base}/{antiga['id']}/avaliacao", headers=auth, json={"valor": valor}
            )
            assert avaliada.status_code == 200, avaliada.text
            assert (await mensagens(cliente, auth, conversa))[-1]["avaliacao"] == valor
        for metodo, sufixo, corpo in (
            ("PUT", "/avaliacao", {"valor": 1}),
            ("POST", "/refazer", None),
            ("PATCH", "", {"texto": "invadido"}),
        ):
            r = await cliente.request(
                metodo, f"{base}/{antiga['id']}{sufixo}", headers=outro, json=corpo
            )
            assert r.status_code == 404
        r = await cliente.post(f"{base}/{antiga['id']}/refazer", headers=auth)
        assert r.status_code == 202, r.text

        async def nova_resposta():
            return [m for m in await resposta() if m["id"] != antiga["id"]]

        nova = (await esperar(nova_resposta))[-1]
        lista = await mensagens(cliente, auth, conversa)
        assert antiga["id"] not in [m["id"] for m in lista]
        pergunta = next(m for m in lista if m["autor"] == "usuario")
        r = await cliente.patch(
            f"{base}/{pergunta['id']}", headers=auth, json={"texto": "pergunta editada"}
        )
        assert r.status_code == 202, r.text
        await esperar(resposta)
        lista = await mensagens(cliente, auth, conversa)
        assert nova["id"] not in [m["id"] for m in lista]
        assert any(m["conteudo"] == "pergunta editada" for m in lista)
        anterior = next(m for m in lista if m["autor"] == "usuario")
        await cliente.post(base, headers=auth, json={"texto": "mais uma"})
        assert (
            await cliente.patch(f"{base}/{anterior['id']}", headers=auth, json={"texto": "antiga"})
        ).status_code == 409
        assert (await cliente.post(f"{base}/{nova['id']}/refazer", headers=auth)).status_code in (
            404,
            409,
        )


@pytest.mark.parametrize("pela_ferramenta", [False, True])
async def test_fontes_persistem_na_resposta(mundo: Mundo, monkeypatch, pela_ferramenta):  # noqa: F811
    modelo = ModeloControlado(
        iniciou=asyncio.Event(),
        cancelou=asyncio.Event(),
        lento=False,
        busca=True,
        pela_ferramenta=pela_ferramenta,
    )
    instalar_modelo(monkeypatch, modelo)
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, f"fontes-{uuid4()}@exemplo.com")
        bot = (
            await cliente.post(
                "/v1/agentes",
                headers=auth,
                json={
                    "nome": "Fontes",
                    "papel": "individual",
                    "funcao": "Pesquisa",
                    "ferramentas": ["buscar_web"],
                },
            )
        ).json()
        conversa = (
            await cliente.post(
                "/v1/conversas", headers=auth, json={"texto": "pesquise", "agente_id": bot["id"]}
            )
        ).json()["id"]
        await mundo.iniciar_worker()

        async def fontes():
            return [m for m in await mensagens(cliente, auth, conversa) if m["fontes"]]

        resposta = (await esperar(fontes))[-1]
        assert resposta["fontes"][0]["n"] == 1
        assert resposta["fontes"][0]["url"].startswith("https://")
        assert (await fontes())[-1]["fontes"] == resposta["fontes"]
        import json

        redis = Redis.from_url(mundo.url_redis, decode_responses=True)
        try:
            eventos = await redis.xrange(canal_conversa(UUID(conversa)))
            finais = [
                json.loads(campos["data"])
                for _, campos in eventos
                if campos["event"] == "mensagem.fim"
            ]
            assert finais[-1]["fontes"] == resposta["fontes"]
        finally:
            await redis.aclose()
