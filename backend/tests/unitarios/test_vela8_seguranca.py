"""Vela-8: achados de segurança do C3 e das aprovações (Cerca A1, A2, A3, M3, B1, B2; Prumo A2).

Cada teste prova o ataque recusado. As rotas com Postgres e Redis de verdade (B3, A2 no servidor,
422 do "sempre") estão em ``tests/integracao/test_vela8_aprovacoes.py``; as regras da ponte, nos
testes Rust (``cargo test pc::``).
"""

from __future__ import annotations

import asyncio
import base64
import io
import time
from typing import Any
from uuid import uuid4

import fakeredis.aioredis
import pytest
from PIL import Image

from app.computador.pc_usuario import (
    ABRIR,
    CAPTURA_OMITIDA,
    PARADO,
    TECLA_PROIBIDA,
    observacao_do_app,
    tecla_proibida,
)
from app.computador.pc_usuario_canal import UMA_VEZ_S, AgentePc, CanalPc
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.revisor.decisoes import aceita_sempre, condicao_da_regra
from app.revisor.esquemas import AcaoProposta
from app.revisor.execucao import acao_do_cartao
from tests.unitarios.test_pc_usuario import (
    AppFalso,
    CartoesFalsos,
    _conectar,
    _erro,
    _observacao,
    _ok,
    _pc,
    _resolvida,
)


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def cartoes() -> CartoesFalsos:
    return CartoesFalsos()


# ---------- Prumo A2 / Cerca M3: regra única do "Sempre permitir" ----------


def test_instrucoes_envio_dominio_e_retomar_nunca_aceitam_sempre() -> None:
    bot = uuid4()
    so_uma_vez = [
        {"ferramenta": "propor_instrucoes", "argumentos": {"texto": "x"}},
        {"ferramenta": "criar_agente"},
        {"ferramenta": "enviar_email", "condicao": {"dominio": "x.com"}},
        {"ferramenta": "mcp__gmail__send_message", "condicao": {"para": "a@b.c"}},
        {"tipo": "rascunho_envio", "ferramenta": "mcp__slack__postar"},
        {"tipo": "aprovar_dominio", "dominio": "x.com"},
        {"tipo": "sugestao_melhoria", "ferramenta": "propor_instrucoes"},
        {"tipo": "pc_retomar", "titulo": "Retomar"},
        {"tipo": "pc_bloqueio", "titulo": "Bloqueio"},
        {"ferramenta": "computador_pc_programa", "condicao": {}},
        {"ferramenta": "computador_pc_programa", "condicao": {"programa": "  "}},
        {"ferramenta": "computador_agir", "argumentos": {"alvo": "pc_usuario", "acoes": []}},
        {"ferramenta": "executar_comando", "argumentos": {"comando": "ls"}},
        {"ferramenta": "chamar_conector", "argumentos": {}},
        {"ferramenta": "navegador_acao", "argumentos": {"ref": "e1"}},
        {"ferramenta": ""},
        None,
        "texto",
    ]
    for acao in so_uma_vez:
        assert not aceita_sempre(acao, bot), acao
        assert condicao_da_regra(acao) is None, acao


def test_sempre_fica_preso_ao_programa_ao_alvo_ou_a_ferramenta_exata() -> None:
    bot = uuid4()
    programa = {"ferramenta": "computador_pc_programa", "condicao": {"programa": "Notepad.exe"}}
    assert condicao_da_regra(programa) == {"programa": "notepad.exe"}
    virtual = {"ferramenta": "computador_agir", "argumentos": {"acoes": []}}  # alvo padrão
    assert condicao_da_regra(virtual) == {"alvo": "virtual"}  # nunca {} (Cerca M3)
    conector = {"ferramenta": "mcp__notion__criar_pagina", "condicao": {}}
    assert condicao_da_regra(conector) == {}  # ferramenta exata do conector
    assert all(aceita_sempre(a, bot) for a in (programa, virtual, conector))
    # sem bot no cartão a regra valeria para todos os bots
    assert not aceita_sempre(programa, None)


def test_cartao_de_computador_nao_guarda_o_texto_digitado() -> None:
    contexto = ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4())
    proposta = AcaoProposta(
        ferramenta="computador_agir",
        argumentos={
            "alvo": "pc_usuario",
            "acoes": [{"tipo": "digitar", "texto": "minha senha é hunter2"}, {"tipo": "clicar"}],
        },
    )
    acao = acao_do_cartao("computador_agir", proposta, contexto, "c1")
    assert "hunter2" not in str(acao)
    assert acao["argumentos"]["acoes"][0]["texto"] == "[21 caracteres]"
    assert acao["argumentos"]["acoes"][1] == {"tipo": "clicar"}
    assert acao["chamada_id"] == "c1"
    outra = AcaoProposta(ferramenta="mcp__x__enviar", argumentos={"texto": "oi"})
    assert acao_do_cartao("mcp__x__enviar", outra, contexto, "c2")["argumentos"]["texto"] == "oi"


# ---------- Cerca A1: atalhos e texto do bot ----------


def test_atalhos_que_abrem_programas_sao_proibidos() -> None:
    for tecla in [
        "ctrl+Escape",
        "ctrl+shift+Escape",
        "alt+Tab",
        "alt+shift+Tab",
        "alt+Escape",
        "super+r",
        "super",
        "Super_L",
        "win+x",
        "ctrl+alt+Delete",
        "F12",
        "ctrl+shift+i",
        "ctrl+shift+J",
        "Menu",
    ]:
        assert tecla_proibida(tecla), tecla
    for tecla in ["Return", "ctrl+l", "ctrl+c", "Escape", "Tab", "shift+Tab", "alt+F4", "F5"]:
        assert not tecla_proibida(tecla), tecla


def test_texto_do_bot_nao_ensina_atalhos_de_sistema() -> None:
    from app.computador.interface import AcaoComputador

    for texto in (ABRIR, TECLA_PROIBIDA, AcaoComputador.model_fields["tecla"].description or ""):
        baixo = texto.lower()
        assert "ctrl+escape" not in baixo and "alt+tab" not in baixo and "win+" not in baixo


async def test_tecla_proibida_nem_chega_ao_app(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    app = AppFalso(computador.canal, usuario_id, sessao_id, lambda _c: _ok())
    with app:
        with pytest.raises(ErroFerramenta, match="não é permitida"):
            await computador.agir(_resolvida(tipo="tecla", tecla="ctrl+Escape"))
        await asyncio.sleep(0.05)
    assert app.recebidos == []


async def test_programa_bloqueado_que_nasce_na_acao_para_e_abre_cartao(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)

    def responder(comando: dict[str, Any]) -> dict[str, Any]:
        if comando["operacao"] == "agir":
            return _erro("processo_bloqueado", programa="C:\\Windows\\System32\\cmd.exe")
        return _ok(_observacao()) if comando["operacao"] == "observar" else _ok()

    app = AppFalso(computador.canal, usuario_id, sessao_id, responder)
    with app:
        cartoes.sempre.add("explorer.exe")
        with pytest.raises(ErroFerramenta, match=r"cmd.exe abriu"):
            await computador.agir(_resolvida(tipo="digitar", texto="cmd\n"))
        await asyncio.sleep(0.1)
        # parado, sem a vez, cartão aberto e a borda apagada (encerrar)
        assert await computador.canal.esta_parado(usuario_id, bot)
        assert await computador.canal.quem_tem_a_vez(usuario_id) is None
        assert [a["tipo"] for _, a, _ in cartoes.abertos] == ["pc_bloqueio"]
        assert "encerrar" in app.operacoes()
        with pytest.raises(ErroFerramenta, match=PARADO[:30]):
            await computador.observar()
        # o usuário permitiu no cartão: volta a valer
        aprovacao_id = cartoes.abertos[0][0]
        cartoes.situacao[aprovacao_id] = "permitida"
        await computador.observar()
        assert not await computador.canal.esta_parado(usuario_id, bot)


def test_captura_omitida_avisa_o_bot() -> None:
    bruta = {**_observacao(), "captura_omitida": "bloqueada_na_frente"}
    observacao = observacao_do_app(bruta)
    # nenhum pixel nem elemento da tela segue adiante, mesmo que a ponte tenha mandado
    assert observacao.arvore == [{"ref": "", "papel": "aviso", "nome": CAPTURA_OMITIDA}]
    original = base64.b64decode(bruta["png"])
    assert observacao.tela.png != original
    with Image.open(io.BytesIO(observacao.tela.png)) as imagem:
        assert imagem.getextrema() == ((0, 0), (0, 0), (0, 0))
        assert imagem.width <= 320
    assert (observacao.tela.largura, observacao.tela.altura) == (64, 40)
    normal = observacao_do_app(_observacao())
    assert normal.arvore is not None and normal.arvore[0]["ref"] == "e1"
    assert normal.tela.png == original
    # a ponte manda png vazio quando omite (nada é copiado da tela): aceito, sem erro
    sem_png = observacao_do_app({**bruta, "png": "", "arvore": []})
    assert sem_png.arvore == observacao.arvore and sem_png.tela.png == observacao.tela.png


def test_tela_do_pc_fica_pouco_no_redis() -> None:
    from app.computador.servico import VALIDADE_CAPTURA_PC_S

    assert VALIDADE_CAPTURA_PC_S <= 5 * 60


# ---------- Cerca A2: esperando cartão, o bot não segura a vez ----------


async def test_esperando_o_cartao_o_bot_solta_a_vez(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    computador.espera_cartao_s = 2
    canal = computador.canal
    vistos: list[bool] = []

    def responder(comando: dict[str, Any]) -> dict[str, Any]:
        if comando["operacao"] == "agir" and "notepad.exe" not in comando["dados"].get(
            "programas_permitidos", []
        ):
            return _erro("programa_nao_permitido", programa="notepad.exe")
        return _ok()

    app = AppFalso(canal, usuario_id, sessao_id, responder)
    with app:
        tarefa = asyncio.create_task(computador.agir(_resolvida(tipo="clicar", x=1, y=1)))
        await asyncio.wait_for(cartoes.aberto.wait(), 5)
        await asyncio.sleep(0.1)
        vistos.append(await canal.bot_no_controle(usuario_id))
        cartoes.situacao[cartoes.abertos[0][0]] = "permitida"
        await asyncio.wait_for(tarefa, 5)
        vistos.append(await canal.bot_no_controle(usuario_id))
    assert vistos == [False, True]


async def test_cartao_do_revisor_solta_a_vez_so_do_proprio_bot(redis, monkeypatch) -> None:
    """Cartão do revisor (ex.: executar_comando) com o bot segurando a vez: ele solta, e o
    usuário decide sem esbarrar no 409. A vez de outro bot fica onde está."""
    from app.revisor import execucao

    monkeypatch.setattr("app.ferramentas.infra.obter_redis", lambda: redis)
    canal, usuario_id = CanalPc(redis), uuid4()
    dono, outro = AgentePc(uuid4(), "Atlas", "#56A8FF"), uuid4()
    await canal.pegar_vez(usuario_id, dono)
    contexto_outro = ContextoFerramenta(usuario_id=usuario_id, agente_id=outro, conversa_id=uuid4())
    await execucao._soltar_vez_do_pc(contexto_outro)
    assert await canal.bot_no_controle(usuario_id)
    contexto = ContextoFerramenta(usuario_id=usuario_id, agente_id=dono.id, conversa_id=uuid4())
    await execucao._soltar_vez_do_pc(contexto)
    assert not await canal.bot_no_controle(usuario_id)


async def test_bot_no_controle_so_com_a_vez_e_sem_pausa(redis) -> None:
    canal, usuario_id = CanalPc(redis), uuid4()
    agente = AgentePc(uuid4(), "Atlas", "#56A8FF")
    assert not await canal.bot_no_controle(usuario_id)
    await canal.pegar_vez(usuario_id, agente)
    assert await canal.bot_no_controle(usuario_id)
    await canal.marcar_pausado(usuario_id, agente.id)
    assert not await canal.bot_no_controle(usuario_id)


# ---------- Cerca B2: "Permitir uma vez" vence ----------


async def test_permitir_uma_vez_vence_e_ler_nao_renova(redis, monkeypatch) -> None:
    canal, usuario_id, bot = CanalPc(redis), uuid4(), uuid4()
    agora = time.time()
    monkeypatch.setattr("app.computador.pc_usuario_canal.time.time", lambda: agora)
    await canal.permitir_uma_vez(usuario_id, bot, "notepad.exe")
    monkeypatch.setattr("app.computador.pc_usuario_canal.time.time", lambda: agora + UMA_VEZ_S - 10)
    await canal.permitir_uma_vez(usuario_id, bot, "mspaint.exe")
    for _ in range(5):  # o worker lê a cada ação: isso não pode estender o prazo
        assert await canal.programas_uma_vez(usuario_id, bot) == {"notepad.exe", "mspaint.exe"}
    monkeypatch.setattr("app.computador.pc_usuario_canal.time.time", lambda: agora + UMA_VEZ_S + 1)
    assert await canal.programas_uma_vez(usuario_id, bot) == {"mspaint.exe"}
    assert UMA_VEZ_S <= 5 * 60
    await canal.marcar_parado(usuario_id, bot)
    assert await canal.programas_uma_vez(usuario_id, bot) == set()
