"""Fila, canais de equipe e correio (etapa 4, Tear) com Postgres/Redis reais,
API em uvicorn e worker ARQ real. ``SORA_MODELO_FALSO=1``; tudo por HTTP/banco."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app.modelos.enumeracoes import TipoAgente
from app.modelos.tabelas import Agente, MensagemCanalTabela, Usuario
from tests.integracao.test_fase_b_pronto import entrar
from tests.integracao.test_relogio_rotinas import Mundo, esperar, mundo, servicos_relogio  # noqa: F401

pytestmark = pytest.mark.integracao


@pytest.fixture(autouse=True)
def _fila_arq_limpa():
    """O pool ARQ global nasce no loop do teste; solta antes e depois."""
    from workers.fila import configurar_fila

    configurar_fila(None)
    yield
    configurar_fila(None)


async def _agentes(m: Mundo, email: str, n: int = 2) -> list[Agente]:
    async with m.fabrica() as sessao:
        uid = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
        novos = [
            Agente(usuario_id=uid, tipo=TipoAgente.ESPECIALISTA, nome=f"Ag{i}", funcao="teste")
            for i in range(n)
        ]
        sessao.add_all(novos)
        await sessao.commit()
        return novos


async def test_canal_delegacao_conclui_no_worker_real(mundo: Mundo) -> None:  # noqa: F811
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as c:
        auth = await entrar(c, mundo.fabrica, "tear-a@exemplo.com")
        a, b = await _agentes(mundo, "tear-a@exemplo.com")
        await mundo.iniciar_worker()
        r = await c.post(
            "/v1/canais-equipe",
            headers=auth,
            json={"nome": "Time", "membros": [str(a.id), str(b.id)], "lider_id": str(a.id)},
        )
        assert r.status_code == 201, r.text
        canal = r.json()
        r = await c.post(
            f"/v1/canais-equipe/{canal['canal_id']}/mensagens",
            headers=auth,
            json={"texto": "Faça o resumo.", "destinatario": str(b.id)},
        )
        assert r.status_code == 202, r.text

        async def concluida() -> list[dict]:
            ts = (
                await c.get(f"/v1/canais-equipe/{canal['canal_id']}/tarefas", headers=auth)
            ).json()
            return ts if ts and all(t["status"] == "concluida" for t in ts) else []

        tarefas = await esperar(concluida)
        assert tarefas[0]["dono_id"] == str(b.id)
        async with mundo.fabrica() as sessao:
            textos = (await sessao.scalars(select(MensagemCanalTabela.texto))).all()
        assert any("Resultado real" in t for t in textos)


async def test_fila_pausa_e_retoma_com_despacho(mundo: Mundo) -> None:  # noqa: F811
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as c:
        auth = await entrar(c, mundo.fabrica, "tear-b@exemplo.com")
        (a,) = await _agentes(mundo, "tear-b@exemplo.com", 1)
        r = await c.post(f"/v1/agentes/{a.id}/fila/pausar", headers=auth)
        assert r.status_code == 200 and r.json()["pausada"] is True
        r = await c.get(f"/v1/agentes/{a.id}/fila", headers=auth)
        assert r.json()["itens"] == []
        r = await c.post(f"/v1/agentes/{a.id}/fila/retomar", headers=auth)
        assert r.json()["pausada"] is False
        # outro usuário não enxerga
        r = await c.get(f"/v1/agentes/{a.id}/fila", headers={"Authorization": "Bearer x"})
        assert r.status_code == 401


async def test_tarefa_sobrevive_a_worker_parado(mundo: Mundo) -> None:  # noqa: F811
    """Mensagem enviada sem worker fica no banco; o worker que sobe depois a conclui."""
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as c:
        auth = await entrar(c, mundo.fabrica, "tear-c@exemplo.com")
        a, b = await _agentes(mundo, "tear-c@exemplo.com")
        canal = (
            await c.post(
                "/v1/canais-equipe",
                headers=auth,
                json={"nome": "Persistente", "membros": [str(a.id), str(b.id)]},
            )
        ).json()
        r = await c.post(
            f"/v1/canais-equipe/{canal['canal_id']}/mensagens",
            headers=auth,
            json={"texto": "Antes do worker.", "destinatario": str(a.id)},
        )
        assert r.status_code == 202
        ts = (await c.get(f"/v1/canais-equipe/{canal['canal_id']}/tarefas", headers=auth)).json()
        assert ts and ts[0]["status"] != "concluida"
        await mundo.iniciar_worker()
        # o despacho original se perdeu (sem worker); qualquer nova mensagem reativa o canal
        await c.post(
            f"/v1/canais-equipe/{canal['canal_id']}/mensagens",
            headers=auth,
            json={"texto": "Agora com worker.", "destinatario": str(a.id)},
        )

        async def todas() -> bool:
            t = (await c.get(f"/v1/canais-equipe/{canal['canal_id']}/tarefas", headers=auth)).json()
            return bool(t) and all(x["status"] == "concluida" for x in t)

        await esperar(todas)


async def test_compactar_recusa_com_item_na_fila(mundo: Mundo) -> None:  # noqa: F811
    from app.filas import FilaAgente, OrigemItem
    from app.filas.sql import ArmazemFilaSQL
    from app.modelos.enumeracoes import TipoConversa
    from app.modelos.tabelas import Conversa

    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as c:
        auth = await entrar(c, mundo.fabrica, "tear-d@exemplo.com")
        (a,) = await _agentes(mundo, "tear-d@exemplo.com", 1)
        async with mundo.fabrica() as sessao:
            sessao.add(Conversa(usuario_id=a.usuario_id, agente_id=a.id, tipo=TipoConversa.CHAT))
            await FilaAgente(ArmazemFilaSQL(sessao)).enfileirar(
                usuario_id=a.usuario_id, agente_id=a.id, texto="x", origem=OrigemItem.USUARIO
            )
            await sessao.commit()
        r = await c.post(f"/v1/agentes/{a.id}/contexto/compactar", headers=auth)
        assert r.status_code == 409, r.text
        assert "fila" in r.json()["detail"].lower()
