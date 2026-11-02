# ruff: noqa: F811
"""Rotas de perfis do navegador (Leme, etapa 4) com Postgres e Redis reais e a API em uvicorn."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app.modelos.tabelas import EstadoNavegador, PerfilNavegador, Usuario
from app.navegador import perfis as pf
from tests.integracao.relogio_base import Mundo, mundo  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar
from tests.integracao.test_navegador_worker import servicos_relogio  # noqa: F401

pytestmark = pytest.mark.integracao

COOKIE = {"name": "sessao", "value": "segredo-do-login", "domain": "banco.exemplo", "path": "/"}


async def _usuario(mundo: Mundo, email: str):
    async with mundo.fabrica() as sessao:
        return await sessao.scalar(select(Usuario.id).where(Usuario.email == email))


async def _gravar(mundo: Mundo, usuario_id, particao: str, aprovados: tuple[str, ...]) -> None:
    estado: dict = {"cookies": [COOKIE], "origins": []}
    for dominio in aprovados:
        estado = pf.com_dominio_aprovado(estado, dominio)
    async with mundo.fabrica() as sessao:
        sessao.add(
            EstadoNavegador(
                particao=particao,
                usuario_id=usuario_id,
                estado_cifrado=pf.cifrar_estado(estado, usuario_id=usuario_id, particao_=particao),
            )
        )
        await sessao.commit()


async def test_listar_revogar_dominio_e_apagar_perfil(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        a = await entrar(cliente, mundo.fabrica, "perfis-a@exemplo.com")
        b = await entrar(cliente, mundo.fabrica, "perfis-b@exemplo.com")
        ua = await _usuario(mundo, "perfis-a@exemplo.com")
        compartilhado = pf.particao(ua, ua, pf.EscolhaPerfil(tipo=pf.TipoPerfil.COMPARTILHADO))
        async with mundo.fabrica() as sessao:
            nomeado = PerfilNavegador(usuario_id=ua, nome="Trabalho", cor="#56A8FF")
            sessao.add(nomeado)
            await sessao.commit()
            perfil_id = nomeado.id
        particao_nomeada = pf.particao(
            ua, ua, pf.EscolhaPerfil(tipo=pf.TipoPerfil.NOMEADO, perfil_id=perfil_id)
        )
        await _gravar(mundo, ua, compartilhado, ("exemplo.com", "banco.exemplo"))
        await _gravar(mundo, ua, particao_nomeada, ("intranet.local",))

        resposta = await cliente.get("/v1/navegador/perfis", headers=a)
        assert resposta.status_code == 200, resposta.text
        assert "segredo-do-login" not in resposta.text and "cookies" not in resposta.text
        lista = {p["nome"]: p for p in resposta.json()}
        assert set(lista) == {"Compartilhado", "Trabalho"}
        assert lista["Compartilhado"]["tipo"] == "compartilhado"
        assert lista["Compartilhado"]["dominios_aprovados"] == ["banco.exemplo", "exemplo.com"]
        assert lista["Trabalho"]["perfil_id"] == str(perfil_id)
        assert lista["Trabalho"]["dominios_aprovados"] == ["intranet.local"]
        assert lista["Trabalho"]["criado_em"] and lista["Trabalho"]["atualizado_em"]
        id_comp = lista["Compartilhado"]["perfil_id"]

        # outro usuário não vê nem mexe
        assert (await cliente.get("/v1/navegador/perfis", headers=b)).json() == []
        for caminho in (f"/v1/navegador/perfis/{perfil_id}", f"/v1/navegador/perfis/{id_comp}"):
            assert (await cliente.delete(caminho, headers=b)).status_code == 404
        revoga_b = await cliente.delete(
            f"/v1/navegador/perfis/{id_comp}/dominios/exemplo.com", headers=b
        )
        assert revoga_b.status_code == 404

        # revoga um domínio: o outro e o login ficam
        ok = await cliente.delete(f"/v1/navegador/perfis/{id_comp}/dominios/exemplo.com", headers=a)
        assert ok.status_code == 204
        de_novo = await cliente.delete(
            f"/v1/navegador/perfis/{id_comp}/dominios/exemplo.com", headers=a
        )
        assert de_novo.status_code == 404
        depois = {
            p["nome"]: p for p in (await cliente.get("/v1/navegador/perfis", headers=a)).json()
        }
        assert depois["Compartilhado"]["dominios_aprovados"] == ["banco.exemplo"]
        async with mundo.fabrica() as sessao:
            linha = await sessao.get(EstadoNavegador, compartilhado)
            estado = pf.decifrar_estado(
                linha.estado_cifrado, usuario_id=ua, particao_=compartilhado
            )
            assert estado["cookies"] == [COOKIE]

        # apaga o nomeado (estado e linha) e o compartilhado (só o estado)
        assert (
            await cliente.delete(f"/v1/navegador/perfis/{perfil_id}", headers=a)
        ).status_code == 204
        assert (
            await cliente.delete(f"/v1/navegador/perfis/{id_comp}", headers=a)
        ).status_code == 204
        assert (await cliente.get("/v1/navegador/perfis", headers=a)).json() == []
        assert (
            await cliente.delete(f"/v1/navegador/perfis/{perfil_id}", headers=a)
        ).status_code == 404
        async with mundo.fabrica() as sessao:
            assert await sessao.get(EstadoNavegador, particao_nomeada) is None
            assert await sessao.get(EstadoNavegador, compartilhado) is None
            assert await sessao.get(PerfilNavegador, perfil_id) is None
        sem_token = await cliente.get("/v1/navegador/perfis")
        assert sem_token.status_code in (401, 403)


async def test_criar_perfil_e_escolher_o_perfil_do_agente(mundo: Mundo) -> None:
    from app.modelos.enumeracoes import TipoAgente
    from app.modelos.tabelas import Agente

    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        a = await entrar(cliente, mundo.fabrica, "perfis-c@exemplo.com")
        b = await entrar(cliente, mundo.fabrica, "perfis-d@exemplo.com")
        ua = await _usuario(mundo, "perfis-c@exemplo.com")
        async with mundo.fabrica() as sessao:
            sora = await sessao.scalar(
                select(Agente.id).where(Agente.usuario_id == ua, Agente.tipo == TipoAgente.SORA)
            )
        assert sora is not None

        criado = await cliente.post("/v1/navegador/perfis", headers=a, json={"nome": " Banco  X "})
        assert criado.status_code == 201, criado.text
        perfil = criado.json()
        assert perfil["nome"] == "Banco X" and perfil["tipo"] == "nomeado"
        assert perfil["dominios_aprovados"] == [] and "cookies" not in criado.text
        duplicado = await cliente.post("/v1/navegador/perfis", headers=a, json={"nome": "banco x"})
        assert duplicado.status_code == 409
        vazio = await cliente.post("/v1/navegador/perfis", headers=a, json={"nome": ""})
        assert vazio.status_code == 422
        # o mesmo nome em outra conta é livre; e ninguém vê o perfil alheio
        outro = await cliente.post("/v1/navegador/perfis", headers=b, json={"nome": "Banco X"})
        assert outro.status_code == 201
        nomes = [p["nome"] for p in (await cliente.get("/v1/navegador/perfis", headers=a)).json()]
        assert nomes == ["Banco X"]

        # escolha do agente: padrão, perfil, efêmero
        url_agente = f"/v1/agentes/{sora}/navegador"
        inicial = (await cliente.get(url_agente, headers=a)).json()
        assert inicial["tipo"] == "compartilhado" and inicial["perfil_id"] is None
        escolhido = await cliente.put(
            url_agente, headers=a, json={"tipo": "perfil", "perfil_id": perfil["perfil_id"]}
        )
        assert escolhido.status_code == 200, escolhido.text
        assert escolhido.json() == {
            "agente_id": str(sora),
            "tipo": "perfil",
            "perfil_id": perfil["perfil_id"],
            "perfil_nome": "Banco X",
        }
        assert (await cliente.get(url_agente, headers=a)).json()["tipo"] == "perfil"
        sem_id = await cliente.put(url_agente, headers=a, json={"tipo": "perfil"})
        assert sem_id.status_code == 422
        efemero = await cliente.put(url_agente, headers=a, json={"tipo": "efemero"})
        assert efemero.json()["tipo"] == "efemero" and efemero.json()["perfil_id"] is None
        invalido = await cliente.put(url_agente, headers=a, json={"tipo": "qualquer"})
        assert invalido.status_code == 422

        # isolamento: agente e perfil de outra conta dão 404
        assert (await cliente.get(url_agente, headers=b)).status_code == 404
        troca = await cliente.put(url_agente, headers=b, json={"tipo": "compartilhado"})
        assert troca.status_code == 404
        perfil_b = (await cliente.get("/v1/navegador/perfis", headers=b)).json()[0]["perfil_id"]
        roubo = await cliente.put(
            url_agente, headers=a, json={"tipo": "perfil", "perfil_id": perfil_b}
        )
        assert roubo.status_code == 404
        alheio = await cliente.post(
            f"/v1/navegador/perfis/{perfil_b}/abrir",
            headers=a,
            json={"url": "http://exemplo.com/"},
        )
        assert alheio.status_code == 404

        # apagar o perfil devolve o agente ao compartilhado
        await cliente.put(
            url_agente, headers=a, json={"tipo": "perfil", "perfil_id": perfil["perfil_id"]}
        )
        apagado = await cliente.delete(f"/v1/navegador/perfis/{perfil['perfil_id']}", headers=a)
        assert apagado.status_code == 204
        assert (await cliente.get(url_agente, headers=a)).json()["tipo"] == "compartilhado"
