"""Contrato HTTP do seletor com banco/Redis reais e provedor sem rede."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.ferramentas.base import ContextoFerramenta
from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import Agente, CanalEquipe, Conversa, ModeloDisponivel
from app.revisor.juiz import AcaoProposta
from tests.integracao.test_provedores import (
    CHAVE_ORIGINAL,
    _cadastrar_e_entrar,
    _usuario_id,
    api,  # noqa: F401
    servicos,  # noqa: F401
)
from tests.unitarios.test_seletor_modelo_permissao import BLOQUEIOS_ABSOLUTOS

pytestmark = pytest.mark.integracao


async def test_preferencias_persistem_modelo_e_isolam_usuario(api):  # noqa: F811
    auth = await _cadastrar_e_entrar(api.cliente)
    outro = await _cadastrar_e_entrar(api.cliente, "outra@exemplo.com")
    conectado = await api.cliente.post(
        "/v1/provedores",
        headers=auth,
        json={"tipo": "openai", "chave": CHAVE_ORIGINAL},
    )
    assert conectado.status_code == 201
    provedor = conectado.json()["provedor"]["id"]
    usuario = await _usuario_id(api)
    async with api.fabrica() as sessao:
        sora = await sessao.scalar(
            select(Agente).where(
                Agente.usuario_id == usuario,
                Agente.tipo == TipoAgente.SORA,
            )
        )
        conversa = Conversa(id=uuid4(), usuario_id=usuario, agente_id=sora.id)
        sessao.add(conversa)
        await sessao.commit()
        alvo = conversa.id
    caminho = f"/v1/conversas/{alvo}/preferencias"
    dados = {
        "provedor_id": provedor,
        "modelo": "openai/gpt-5.6-luna",
        "raciocinio": "alto",
        "permissao": "automatico",
    }
    resposta = await api.cliente.patch(caminho, headers=auth, json=dados)
    assert resposta.status_code == 200, resposta.text
    for chave, valor in dados.items():
        assert resposta.json()[chave] == valor
    assert (await api.cliente.get(caminho, headers=auth)).json() == resposta.json()
    assert (await api.cliente.get(caminho, headers=outro)).status_code == 404
    assert (await api.cliente.patch(caminho, headers=outro, json=dados)).status_code == 404
    recusado = await api.cliente.patch(caminho, headers=auth, json={"permissao": "total"})
    assert recusado.status_code == 422 and "confirme" in recusado.json()["detail"]
    confirmado = await api.cliente.patch(
        caminho, headers=auth, json={"permissao": "total", "confirmar_total": True}
    )
    assert confirmado.status_code == 200 and confirmado.json()["modelo"] == dados["modelo"]


async def test_catalogo_ativo_filtra_chat_e_adiciona_modelo_so_para_dono(api):  # noqa: F811
    auth = await _cadastrar_e_entrar(api.cliente)
    outro = await _cadastrar_e_entrar(api.cliente, "outra@exemplo.com")
    api.listador.respostas[CHAVE_ORIGINAL] = [
        "openai/gpt-4o",
        "openai/o3",
        "openai/whisper-1",
        "openai/text-embedding-3-small",
    ]
    resposta = await api.cliente.post(
        "/v1/provedores", headers=auth, json={"tipo": "openai", "chave": CHAVE_ORIGINAL}
    )
    assert resposta.status_code == 201
    assert all(m["ativo"] for m in resposta.json()["modelos"])
    provedor = resposta.json()["provedor"]["id"]
    modelos = (await api.cliente.get("/v1/modelos", headers=auth)).json()
    assert {m["modelo"] for m in modelos} == {"openai/gpt-4o", "openai/o3"}
    assert all(m["principal"] and isinstance(m["rapido"], bool) for m in modelos)
    assert next(m for m in modelos if m["modelo"] == "openai/o3")["raciocinio"] == [
        "baixo",
        "medio",
        "alto",
    ]
    api.listador.respostas[CHAVE_ORIGINAL].append("openai/gpt-4.1")
    caminho = f"/v1/provedores/{provedor}/modelos"
    adicionado = await api.cliente.post(caminho, headers=auth, json={"id": "gpt-4.1"})
    assert adicionado.status_code == 201, adicionado.text
    assert adicionado.json()["modelo"] == "openai/gpt-4.1" and adicionado.json()["ativo"]
    repetido = await api.cliente.post(caminho, headers=auth, json={"id": "gpt-4.1"})
    assert repetido.json()["id"] == adicionado.json()["id"]
    assert (
        await api.cliente.post(caminho, headers=outro, json={"id": "gpt-4.1"})
    ).status_code == 404
    assert (
        await api.cliente.post(caminho, headers=auth, json={"id": "inexistente"})
    ).status_code == 422
    async with api.fabrica() as sessao:
        assert len(list(await sessao.scalars(select(ModeloDisponivel)))) == 5


async def test_bot_e_grupo_herdam_e_persistem_preferencias(api):  # noqa: F811
    auth = await _cadastrar_e_entrar(api.cliente)
    conectado = await api.cliente.post(
        "/v1/provedores", headers=auth, json={"tipo": "openai", "chave": CHAVE_ORIGINAL}
    )
    dados = {
        "provedor_id": conectado.json()["provedor"]["id"],
        "modelo": "openai/gpt-5.6-luna",
        "raciocinio": "baixo",
        "permissao": "automatico",
    }
    usuario = await _usuario_id(api)
    async with api.fabrica() as sessao:
        bot = Agente(usuario_id=usuario, nome="QA", tipo=TipoAgente.INDIVIDUAL)
        sessao.add(bot)
        await sessao.flush()
        conversa = Conversa(usuario_id=usuario, agente_id=bot.id)
        grupo = CanalEquipe(usuario_id=usuario, nome="QA grupo")
        sessao.add_all([conversa, grupo])
        await sessao.commit()
    atualizado = await api.cliente.patch(f"/v1/agentes/{bot.id}", headers=auth, json=dados)
    assert atualizado.status_code == 200, atualizado.text
    for chave, valor in dados.items():
        assert atualizado.json()[chave] == valor
    herdado = (
        await api.cliente.get(f"/v1/conversas/{conversa.id}/preferencias", headers=auth)
    ).json()
    assert herdado["origem"] == "bot" and herdado["modelo"] == dados["modelo"]
    caminho = f"/v1/conversas/{grupo.id}/preferencias"
    alterado = await api.cliente.patch(caminho, headers=auth, json=dados)
    assert alterado.status_code == 200 and alterado.json()["tipo"] == "grupo"
    assert (await api.cliente.get(caminho, headers=auth)).json() == alterado.json()


async def test_permissao_real_registra_e_bloqueios_nao_chegam_ao_juiz(api, monkeypatch):  # noqa: F811
    from app.modelos.tabelas import RegistroAcao
    from app.revisor import execucao
    from app.revisor.decisoes import nome_real
    from app.revisor.politica import Politica, politica_da_ferramenta

    await _cadastrar_e_entrar(api.cliente)
    usuario = await _usuario_id(api)
    async with api.fabrica() as sessao:
        sora = await sessao.scalar(select(Agente).where(Agente.usuario_id == usuario))

    @asynccontextmanager
    async def abrir():
        async with api.fabrica() as sessao:
            yield sessao
            await sessao.commit()

    eventos = []

    async def emitir(_contexto, evento):
        eventos.append(evento)

    class Cartao(Exception):
        pass

    async def cartao(*args, **kwargs):
        raise Cartao()

    async def nunca(*args, **kwargs):
        raise AssertionError("Bloqueio permanente chegou ao juiz ou à regra")

    monkeypatch.setattr(execucao, "abrir_sessao", abrir)
    monkeypatch.setattr(execucao, "emitir", emitir)
    monkeypatch.setattr(execucao, "_abrir_cartao", cartao)
    monkeypatch.setattr("app.revisor.acoes.regra_permite", nunca)
    monkeypatch.setattr("app.revisor.juiz.avaliar_acao", nunca)
    contexto = ContextoFerramenta(
        usuario_id=usuario, agente_id=sora.id, conversa_id=uuid4(), permissao="total"
    )
    await execucao.conferir_acao("executar_comando", {"comando": "ls"}, contexto, chamada_id="qa")
    async with api.fabrica() as sessao:
        linhas = list(await sessao.scalars(select(RegistroAcao)))
        assert len(linhas) == 1 and "modo total" in linhas[0].resumo
    assert eventos[0].texto.startswith("Aprovado automaticamente (modo total)")
    # Exercita a integração do revisor com os mesmos bloqueios, sem chamar uma ferramenta real.
    for modo in ("perguntar", "automatico", "total"):
        from dataclasses import replace

        contexto = replace(contexto, permissao=modo)
        for acao in BLOQUEIOS_ABSOLUTOS.values():

            async def preparar(*args, acao=acao, **kwargs):
                return AcaoProposta(
                    ferramenta=acao["ferramenta"], argumentos=acao.get("argumentos", {})
                )

            # Tipos exclusivos do PC/sugestão têm seus próprios cartões, testados na suíte unitária.
            if (
                acao.get("tipo")
                or acao["ferramenta"] == "propor_instrucoes"
                or politica_da_ferramenta(nome_real(acao), somente_leitura=False) is Politica.LIVRE
            ):
                continue
            monkeypatch.setattr(execucao, "_preparar_acao", preparar)
            with pytest.raises(Cartao):
                await execucao.conferir_acao(
                    nome_real(acao),
                    acao.get("argumentos", {}),
                    contexto,
                    chamada_id=str(uuid4()),
                    somente_leitura=False,
                )
