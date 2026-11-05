"""Fila, canais de equipe e correio (etapa 4, Tear) com Postgres/Redis reais,
API em uvicorn e worker ARQ real. ``SORA_MODELO_FALSO=1``; tudo por HTTP/banco."""

from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select

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


@pytest.mark.parametrize("como", ["arquivar", "cancelar"])
async def test_job_de_tarefa_que_nao_espera_mais_sai_limpo(mundo: Mundo, como: str) -> None:  # noqa: F811
    """Canal arquivado/tarefa cancelada com o job já na fila do ARQ: o job termina com
    sucesso (sem exceção, logo sem retry) e a tarefa continua como o usuário deixou."""
    from arq.jobs import Job

    from workers.fila import enfileirar, obter_fila

    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as c:
        auth = await entrar(c, mundo.fabrica, f"tear-e-{como}@exemplo.com")
        a, b = await _agentes(mundo, f"tear-e-{como}@exemplo.com")
        canal = (
            await c.post(
                "/v1/canais-equipe",
                headers=auth,
                json={"nome": "Cancelavel", "membros": [str(a.id), str(b.id)]},
            )
        ).json()
        cid = canal["canal_id"]
        r = await c.post(
            f"/v1/canais-equipe/{cid}/mensagens",
            headers=auth,
            json={"texto": "Vai ser cancelada.", "destinatario": str(a.id)},
        )
        assert r.status_code == 202
        tarefa = (await c.get(f"/v1/canais-equipe/{cid}/tarefas", headers=auth)).json()[0]
        if como == "arquivar":
            r = await c.post(f"/v1/canais-equipe/{cid}/arquivar", headers=auth)
        else:
            tid = tarefa["tarefa_id"]
            await c.post(f"/v1/tarefas-canal/{tid}/parar", headers=auth)
            r = await c.post(f"/v1/tarefas-canal/{tid}/cancelar", headers=auth)
        assert r.status_code in (200, 204), r.text
        antes = next(
            t
            for t in (await c.get(f"/v1/canais-equipe/{cid}/tarefas", headers=auth)).json()
            if t["tarefa_id"] == tarefa["tarefa_id"]
        )["status"]
        assert antes != "na_fila"

        job_id = f"tear-ignorada-{como}"
        await enfileirar("executar_tarefa_canal", id_job=job_id, tarefa_id=tarefa["tarefa_id"])
        await mundo.iniciar_worker()
        job = Job(job_id, await obter_fila())

        async def terminou():
            return await job.result_info()

        info = await esperar(terminou)
        assert info.success is True, info.result
        depois = next(
            t
            for t in (await c.get(f"/v1/canais-equipe/{cid}/tarefas", headers=auth)).json()
            if t["tarefa_id"] == tarefa["tarefa_id"]
        )["status"]
        assert depois == antes


# ---------------------------------------------------------------- rodada 4 (Aferidor)


async def _conversa(m: Mundo, agente: Agente) -> UUID:
    from app.modelos.enumeracoes import TipoConversa
    from app.modelos.tabelas import Conversa

    async with m.fabrica() as sessao:
        conversa = Conversa(
            usuario_id=agente.usuario_id, agente_id=agente.id, tipo=TipoConversa.CHAT
        )
        sessao.add(conversa)
        await sessao.commit()
        return conversa.id


async def _perguntar_sem_job(m: Mundo, conversa_id: UUID, texto: str) -> UUID:
    from app.modelos.enumeracoes import AutorMensagem
    from app.modelos.tabelas import Mensagem

    async with m.fabrica() as sessao:
        mensagem = Mensagem(conversa_id=conversa_id, autor=AutorMensagem.USUARIO, conteudo=texto)
        sessao.add(mensagem)
        await sessao.commit()
        return mensagem.id


async def _perguntar(m: Mundo, conversa_id: UUID, texto: str) -> None:
    """Grava a mensagem do usuario e enfileira o job, como a API faz."""
    from workers.fila import enfileirar

    mensagem_id = await _perguntar_sem_job(m, conversa_id, texto)
    await enfileirar("responder_direto", mensagem_id=str(mensagem_id))


async def _respostas(m: Mundo, conversa_id: UUID) -> int:
    from app.modelos.enumeracoes import AutorMensagem
    from app.modelos.tabelas import Mensagem

    async with m.fabrica() as sessao:
        total = await sessao.scalar(
            select(func.count())
            .select_from(Mensagem)
            .where(Mensagem.conversa_id == conversa_id, Mensagem.autor != AutorMensagem.USUARIO)
        )
        return int(total or 0)


async def _itens(m: Mundo, agente_id: UUID) -> list:
    from app.modelos.tabelas import FilaMensagem

    async with m.fabrica() as sessao:
        linhas = await sessao.scalars(
            select(FilaMensagem)
            .where(FilaMensagem.agente_id == agente_id)
            .order_by(FilaMensagem.seq)
        )
        return list(linhas.all())


async def _item_em_andamento(m: Mundo, agente: Agente, texto: str) -> UUID:
    """Item reservado e rodando, como o worker o deixa no meio de um turno."""
    from app.filas import FilaAgente, OrigemItem
    from app.filas.sql import ArmazemFilaSQL

    async with m.fabrica() as sessao:
        fila = FilaAgente(ArmazemFilaSQL(sessao))
        item = await fila.enfileirar(
            usuario_id=agente.usuario_id,
            agente_id=agente.id,
            texto=texto,
            origem=OrigemItem.USUARIO,
        )
        await fila.iniciar(item.id, agente.id)
        await fila.rodando(item.id, agente.id)
        await sessao.commit()
        return item.id


async def test_fila_pausada_e_retomada_responde_de_verdade(mundo: Mundo) -> None:  # noqa: F811
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as c:
        auth = await entrar(c, mundo.fabrica, "tear-f@exemplo.com")
        (a,) = await _agentes(mundo, "tear-f@exemplo.com", 1)
        conversa = await _conversa(mundo, a)
        await mundo.iniciar_worker()
        assert (await c.post(f"/v1/agentes/{a.id}/fila/pausar", headers=auth)).status_code == 200
        await _perguntar(mundo, conversa, "Oi, pausado.")

        async def na_fila() -> bool:
            return any(i.status == "na_fila" for i in await _itens(mundo, a.id))

        await esperar(na_fila)
        await asyncio.sleep(2)
        assert await _respostas(mundo, conversa) == 0  # pausada: ninguem responde
        assert (await c.post(f"/v1/agentes/{a.id}/fila/retomar", headers=auth)).status_code == 200

        async def respondida() -> bool:
            return await _respostas(mundo, conversa) >= 1

        await esperar(respondida)

        async def concluido() -> bool:
            return [i.status for i in await _itens(mundo, a.id)] == ["concluido"]

        await esperar(concluido)


async def test_segunda_mensagem_a_agente_ocupado_e_respondida(
    mundo: Mundo,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import workers.conversa as conversa_mod

    liberar = asyncio.Event()
    chamadas = 0
    original = conversa_mod._responder_direto_sem_fila

    async def lenta(*args, **kwargs):
        nonlocal chamadas
        chamadas += 1
        if chamadas == 1:
            await liberar.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(conversa_mod, "_responder_direto_sem_fila", lenta)
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as c:
        await entrar(c, mundo.fabrica, "tear-g@exemplo.com")
        (a,) = await _agentes(mundo, "tear-g@exemplo.com", 1)
        conversa = await _conversa(mundo, a)
        await mundo.iniciar_worker()
        await _perguntar(mundo, conversa, "Primeira.")

        async def rodando() -> bool:
            return any(i.status == "rodando" for i in await _itens(mundo, a.id))

        await esperar(rodando)
        await _perguntar(mundo, conversa, "Segunda, com o agente ocupado.")

        async def dois_itens() -> bool:
            return len(await _itens(mundo, a.id)) == 2

        await esperar(dois_itens)
        await asyncio.sleep(1)
        assert await _respostas(mundo, conversa) == 0
        liberar.set()

        async def duas_respostas() -> bool:
            return await _respostas(mundo, conversa) >= 2

        await esperar(duas_respostas)


async def test_repetir_item_interrompido_responde(mundo: Mundo) -> None:  # noqa: F811
    from app.filas import FilaAgente
    from app.filas.sql import ArmazemFilaSQL

    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as c:
        auth = await entrar(c, mundo.fabrica, "tear-h@exemplo.com")
        (a,) = await _agentes(mundo, "tear-h@exemplo.com", 1)
        conversa = await _conversa(mundo, a)
        await _perguntar_sem_job(mundo, conversa, "Pedido que caiu.")
        item_id = await _item_em_andamento(mundo, a, "Pedido que caiu.")
        async with mundo.fabrica() as sessao:
            await FilaAgente(ArmazemFilaSQL(sessao)).recuperar_apos_queda()
            await sessao.commit()
        await mundo.iniciar_worker()
        r = await c.post(f"/v1/agentes/{a.id}/fila/{item_id}/repetir", headers=auth)
        assert r.status_code == 200, r.text

        async def respondida() -> bool:
            return await _respostas(mundo, conversa) >= 1

        await esperar(respondida)


async def test_recuperacao_nao_derruba_turno_vivo_de_outro_worker(mundo: Mundo) -> None:  # noqa: F811
    from redis.asyncio import Redis

    from app.modelos.tabelas import TarefaCanalTabela
    from workers.equipe import recuperar_equipe_apos_queda

    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as c:
        auth = await entrar(c, mundo.fabrica, "tear-i@exemplo.com")
        a, b = await _agentes(mundo, "tear-i@exemplo.com")
        vivo = await _item_em_andamento(mundo, a, "vivo")
        morto = await _item_em_andamento(mundo, b, "morto")
        canal = (
            await c.post(
                "/v1/canais-equipe",
                headers=auth,
                json={"nome": "Dois workers", "membros": [str(a.id), str(b.id)]},
            )
        ).json()
        cid = canal["canal_id"]
        for dono in (a, b):
            await c.post(
                f"/v1/canais-equipe/{cid}/mensagens",
                headers=auth,
                json={"texto": "x", "destinatario": str(dono.id)},
            )
        tarefas = (await c.get(f"/v1/canais-equipe/{cid}/tarefas", headers=auth)).json()
        assert len(tarefas) == 2
        async with mundo.fabrica() as sessao:
            for t in tarefas:
                linha = await sessao.get(TarefaCanalTabela, UUID(t["tarefa_id"]))
                linha.status = "rodando"
            await sessao.commit()
        redis = Redis.from_url(mundo.url_redis)
        # outro worker esta vivo no primeiro item e na primeira tarefa
        await redis.set(f"batimento:{vivo}", "1", ex=60)
        await redis.set(f"batimento:{tarefas[0]['tarefa_id']}", "1", ex=60)
        try:
            await recuperar_equipe_apos_queda({"sessoes": mundo.fabrica, "redis_eventos": redis})
        finally:
            await redis.aclose()
        itens = {i.id: i.status for i in await _itens(mundo, a.id) + await _itens(mundo, b.id)}
        assert itens[vivo] == "rodando"
        assert itens[morto] == "interrompido"
        atuais = {
            t["tarefa_id"]: t["status"]
            for t in (await c.get(f"/v1/canais-equipe/{cid}/tarefas", headers=auth)).json()
        }
        assert atuais[tarefas[0]["tarefa_id"]] == "rodando"
        assert atuais[tarefas[1]["tarefa_id"]] == "parada"


@pytest.mark.parametrize("como", ["parar", "cancelar"])
async def test_parar_e_cancelar_interrompem_o_turno_em_andamento(
    mundo: Mundo,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    como: str,
) -> None:
    import workers.equipe as equipe_mod

    iniciou, cancelado = asyncio.Event(), asyncio.Event()

    async def turno_longo(ctx, tarefa, revisao):
        iniciou.set()
        try:
            await asyncio.sleep(120)
        finally:
            cancelado.set()

    monkeypatch.setattr(equipe_mod, "_turno_falso", turno_longo)
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as c:
        auth = await entrar(c, mundo.fabrica, f"tear-j-{como}@exemplo.com")
        a, b = await _agentes(mundo, f"tear-j-{como}@exemplo.com")
        await mundo.iniciar_worker()
        canal = (
            await c.post(
                "/v1/canais-equipe",
                headers=auth,
                json={"nome": "Parar", "membros": [str(a.id), str(b.id)]},
            )
        ).json()
        cid = canal["canal_id"]
        await c.post(
            f"/v1/canais-equipe/{cid}/mensagens",
            headers=auth,
            json={"texto": "demora", "destinatario": str(a.id)},
        )
        await asyncio.wait_for(iniciou.wait(), 30)
        tarefas = (await c.get(f"/v1/canais-equipe/{cid}/tarefas", headers=auth)).json()
        tid = tarefas[0]["tarefa_id"]
        await c.post(f"/v1/tarefas-canal/{tid}/parar", headers=auth)
        if como == "cancelar":
            r = await c.post(f"/v1/tarefas-canal/{tid}/cancelar", headers=auth)
            assert r.status_code == 200, r.text
        await asyncio.wait_for(cancelado.wait(), 10)  # o turno parou de verdade


async def test_trava_do_canal_cobre_a_tarefa_neta(mundo: Mundo) -> None:  # noqa: F811
    from sqlalchemy.exc import DBAPIError

    from app.canais_equipe.sql import ArmazemCanaisSQL
    from app.modelos.tabelas import TarefaCanalTabela

    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as c:
        auth = await entrar(c, mundo.fabrica, "tear-k@exemplo.com")
        a, b = await _agentes(mundo, "tear-k@exemplo.com")
        canal = (
            await c.post(
                "/v1/canais-equipe",
                headers=auth,
                json={"nome": "Netas", "membros": [str(a.id), str(b.id)]},
            )
        ).json()
        cid = canal["canal_id"]
        await c.post(
            f"/v1/canais-equipe/{cid}/mensagens",
            headers=auth,
            json={"texto": "x", "destinatario": str(a.id)},
        )
        avo = (await c.get(f"/v1/canais-equipe/{cid}/tarefas", headers=auth)).json()[0]
        avo_id = UUID(avo["tarefa_id"])
        async with mundo.fabrica() as sessao:
            raiz = await sessao.get(TarefaCanalTabela, avo_id)
            mae = TarefaCanalTabela(
                canal_id=raiz.canal_id,
                pedido_id=raiz.pedido_id,
                dono_id=b.id,
                instrucao="mae",
                raiz_id=avo_id,
                pai_id=avo_id,
            )
            sessao.add(mae)
            await sessao.flush()
            neta = TarefaCanalTabela(
                canal_id=raiz.canal_id,
                pedido_id=raiz.pedido_id,
                dono_id=a.id,
                instrucao="neta",
                raiz_id=avo_id,
                pai_id=mae.id,
            )
            sessao.add(neta)
            await sessao.commit()
            neta_id = neta.id
        async with mundo.fabrica() as dona, mundo.fabrica() as outra:
            async with ArmazemCanaisSQL(dona).transacao_tarefa(neta_id):
                with pytest.raises(DBAPIError):
                    await outra.scalar(
                        select(TarefaCanalTabela.id)
                        .where(TarefaCanalTabela.id == avo_id)
                        .with_for_update(nowait=True)
                    )
