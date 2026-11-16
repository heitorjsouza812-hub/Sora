"""Contrato HTTP do seletor com banco/Redis reais e provedor sem rede."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import Agente, Conversa
from tests.integracao.test_provedores import (
    CHAVE_ORIGINAL,
    _cadastrar_e_entrar,
    _usuario_id,
    api,  # noqa: F401
    servicos,  # noqa: F401
)

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
