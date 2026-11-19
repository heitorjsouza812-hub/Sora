"""Regress?es da montagem enxuta do Motor-2."""

import json
from uuid import uuid4

from langchain_core.utils.function_calling import convert_to_openai_tool

from app.agentes.ancora import catalogo_enxuto
from app.agentes.ferramentas_do_turno import nomes_diretos
from app.agentes.montagem import ContextoAgente, montar_prompt_de_sistema, nomes_das_ferramentas
from app.ferramentas.base import ContextoFerramenta
from app.ferramentas.catalogo_preguicoso import CatalogoFerramentas
from app.ferramentas.registro import criar_ferramentas


def test_bot_simples_tem_esquemas_enxutos_e_navegador_sob_demanda():
    c = ContextoAgente(
        usuario_id=uuid4(),
        agente_id=uuid4(),
        conversa_id=uuid4(),
        papel="individual",
        ferramentas_do_bot=[],
    )
    ferramentas = criar_ferramentas(
        nomes_das_ferramentas(c),
        ContextoFerramenta(
            usuario_id=c.usuario_id, agente_id=c.agente_id, conversa_id=c.conversa_id
        ),
    )
    diretos = set(nomes_diretos([f.name for f in ferramentas], c))
    escondidas = [f for f in ferramentas if f.name not in diretos]
    oferecidas = [f for f in ferramentas if f.name in diretos] + catalogo_enxuto(escondidas, [], c)
    esquemas = json.dumps([convert_to_openai_tool(f) for f in oferecidas], ensure_ascii=False)
    # Teto contra crescimento sem querer, não amarrado ao plano grátis da Groq (que só existe nos
    # testes; Heitor, 2026-11-18). Agenda e ferramentas de conversa vão direto: o modelo não as
    # achava no catálogo. ~3 mil tokens por chamada num bot simples.
    assert len(esquemas) < 16000
    assert {"agendar", "listar_agendamentos", "cancelar_agendamento"} <= diretos
    assert {"listar_pendencias", "buscar_historico", "enviar_para_agente"} <= diretos
    assert "navegador_acao" not in diretos
    assert "navegador_acao" not in {f.name for f in escondidas}
    assert len(montar_prompt_de_sistema(c)) < 9000  # mesmo critério do teto acima


def test_catalogo_entrega_esquema_com_regras():
    c = ContextoAgente(
        usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4(), papel="individual"
    )
    ferramentas = criar_ferramentas(
        ["buscar_memoria"],
        ContextoFerramenta(
            usuario_id=c.usuario_id, agente_id=c.agente_id, conversa_id=c.conversa_id
        ),
    )
    catalogo = CatalogoFerramentas(ferramentas, guias={"buscar_memoria": "Confira a atualidade."})
    entrada = catalogo.carregar("buscar_memoria")
    assert entrada["esquema"]
    assert entrada["regras_de_uso"] == "Confira a atualidade."


async def test_streaming_publica_antes_de_terminar_sem_argumentos_privados():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.agentes.middleware.conversa import TextoParcial

    fluxo = SimpleNamespace(publicar=AsyncMock())
    callback = TextoParcial(fluxo)
    await callback.on_llm_new_token("Olá")
    fluxo.publicar.assert_awaited_with("Olá")
    chunk = SimpleNamespace(
        message=SimpleNamespace(
            tool_call_chunks=[
                {"index": 0, "name": "executar_comando", "args": '{"texto":"segredo"}'}
            ]
        )
    )
    await callback.on_llm_new_token("", chunk=chunk)
    assert callback.parcial() == "Olá"
    chunk.message.tool_call_chunks = [{"index": 1, "name": "falar", "args": '{"texto":"Resposta'}]
    await callback.on_llm_new_token("", chunk=chunk)
    fluxo.publicar.assert_awaited_with("Resposta")


def test_fontes_nao_absorvem_quebra_escapada():
    from app.agentes.middleware.conversa import coletar_fontes

    fontes = []
    coletar_fontes("https://example.com/\\nLeitura concluida", fontes)
    assert fontes[0]["url"] == "https://example.com/"


async def test_duckduckgo_recusa_captcha_e_pagina_vazia():
    import httpx
    import pytest

    from app.busca.duckduckgo import BuscaDuckDuckGo
    from app.busca.provedor import ErroBusca

    for pagina in ("<html>captcha</html>", "<html></html>"):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request, pagina=pagina: httpx.Response(200, text=pagina)
            )
        ) as cliente:
            with pytest.raises(ErroBusca):
                await BuscaDuckDuckGo(cliente=cliente).buscar("Sora")


def test_cota_diaria_informa_prazo_sem_segredo():
    from app.llm.limite import cota_diaria, erro_cota_diaria

    erro = ValueError("tokens per day (TPD). Try again in 2h3m4s. token secreto")
    assert cota_diaria(erro)
    mensagem = str(erro_cota_diaria(erro))
    assert "7385" in mensagem
    assert "secreto" not in mensagem
    assert "outro modelo" in mensagem


async def test_orpheus_usa_voz_e_formato_nativos():
    import httpx

    from app.voz.provedores import VozOpenAI

    pedidos = []

    def responder(request):
        pedidos.append(json.loads(request.content))
        return httpx.Response(200, content=b"RIFF")

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        voz = VozOpenAI("teste", cliente=cliente)
        voz.modelo_fala = "canopylabs/orpheus-v1-english"
        audio = await voz.sintetizar("Hello")
    assert pedidos[0]["voice"] == "troy"
    assert pedidos[0]["response_format"] == "wav"
    assert audio.tipo == "audio/wav"


def test_voz_remove_prefixo_litellm_do_groq():
    from app.voz.modelos import modelo_de_fala, modelo_de_transcricao

    assert modelo_de_transcricao(["groq/whisper-large-v3"]) == "whisper-large-v3"
    assert modelo_de_fala(["groq/canopylabs/orpheus-v1-english"]) == "canopylabs/orpheus-v1-english"


def test_tres_limites_do_provedor_tem_mensagens_distintas():
    from app.llm.limite import ErroLimiteDoProvedor

    minuto = str(ErroLimiteDoProvedor("limite por minuto"))
    grande = str(ErroLimiteDoProvedor("pedido grande demais"))
    dia = str(ErroLimiteDoProvedor("cota do dia: tente novamente em 60 segundos"))
    assert len({minuto, grande, dia}) == 3
    assert "minuto" in minuto
    assert "Compacte" in grande and "outro modelo" in grande
    assert "60 segundos" in dia and "outro modelo" in dia


def test_fontes_ignoram_pagina_de_erro_do_buscador_e_url_malformada():
    from app.agentes.middleware.conversa import coletar_fontes

    fontes: list[dict] = []
    coletar_fontes(
        "1. Erro\nhttps://duckduckgo.com/static-pages/home-error/418.html\n"
        "2. Python\nhttps://www.python.org/downloads/\nLeitura\n"
        "3. Sem domínio\nhttp://localhost/x\n",
        fontes,
    )
    assert [f["url"] for f in fontes] == ["https://www.python.org/downloads/"]


async def test_ouvir_com_erro_do_provedor_nao_vira_502(monkeypatch):
    import pytest
    from fastapi import HTTPException

    from app.api import voz as api_voz
    from app.voz.provedores import ErroVoz

    class VozQuebrada:
        async def sintetizar(self, texto, voz):
            raise ErroVoz("O Groq exige que o administrador aceite os termos.")

    async def falsa(*_args):
        return VozQuebrada()

    monkeypatch.setattr(api_voz, "_voz_do_usuario", falsa)
    with pytest.raises(HTTPException) as erro:
        await api_voz.falar_texto(api_voz.Fala(texto="Olá"), uuid4(), None)
    assert erro.value.status_code != 502
    assert "termos" in erro.value.detail


async def test_chamada_de_ferramenta_malformada_e_repetida_uma_vez_e_depois_sobe():
    import pytest

    from app.agentes.middleware.limite_provedor import MiddlewareLimiteDoProvedor

    class Pedido:
        messages: list = []  # noqa: RUF012

        def override(self, **_):
            return self

    chamadas = []

    async def so_falha_na_primeira(_pedido):
        chamadas.append(1)
        if len(chamadas) == 1:
            raise ValueError("invalid literal for int(): 'tool_use_failed'")
        return "ok"

    middleware = MiddlewareLimiteDoProvedor()
    assert await middleware.awrap_model_call(Pedido(), so_falha_na_primeira) == "ok"
    assert len(chamadas) == 2

    async def sempre_falha(_pedido):
        raise ValueError("Tool call validation failed: which was not in request.tools")

    with pytest.raises(ValueError):
        await middleware.awrap_model_call(Pedido(), sempre_falha)
