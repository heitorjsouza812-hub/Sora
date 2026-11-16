from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import delete, func, select

from app.eventos.streams import canal_usuario
from app.modelos.enumeracoes import StatusAprovacao, TipoAgente, TipoConversa
from app.modelos.tabelas import (
    Agente,
    Aprovacao,
    CanalEquipe,
    Conversa,
    Mensagem,
    Pergunta,
    PropostaGrupo,
    RascunhoBot,
    Rotina,
    Usuario,
)
from tests.integracao.relogio_base import Mundo, mundo  # noqa: F401
from tests.integracao.relogio_base import servicos_relogio as _servicos_testcontainers
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


@pytest.fixture(scope="module")
def servicos_relogio():
    """Usa os serviços da etapa 5 quando informados; senão cria contêineres descartáveis."""
    if os.environ.get("SORA_TESTE_PG") and os.environ.get("SORA_TESTE_REDIS"):
        yield os.environ["SORA_TESTE_PG"], os.environ["SORA_TESTE_REDIS"]
        return
    yield from _servicos_testcontainers.__wrapped__()


async def test_bloco_1_sora_persistente_e_saida_dos_bots(mundo: Mundo) -> None:  # noqa: F811
    email = f"etapa5-bloco1-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        inicial = await cliente.get("/v1/agentes/sora", headers=auth)
        assert inicial.status_code == 200, inicial.text
        corpo = inicial.json()
        assert corpo["tipo"] == "sora"
        assert corpo["cor"] == "#E2ECFF"
        assert corpo["estado"] == "livre"
        assert "perguntar" in corpo["ferramentas"]

        # Simula conta antiga: duas leituras concorrentes precisam criar exatamente uma Sora.
        async with mundo.fabrica() as sessao:
            usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
            await sessao.execute(
                delete(Agente).where(
                    Agente.usuario_id == usuario_id, Agente.tipo == TipoAgente.SORA
                )
            )
            await sessao.commit()

        primeira, segunda = await asyncio.gather(
            cliente.get("/v1/agentes/sora", headers=auth),
            cliente.get("/v1/agentes/sora", headers=auth),
        )
        assert primeira.status_code == segunda.status_code == 200
        assert primeira.json()["id"] == segunda.json()["id"]

        lista = (await cliente.get("/v1/agentes", headers=auth)).json()
        sora = [agente for agente in lista if agente["tipo"] == "sora"]
        assert len(sora) == 1
        assert sora[0]["ferramentas"] == primeira.json()["ferramentas"]
        async with mundo.fabrica() as sessao:
            total = await sessao.scalar(
                select(func.count())
                .select_from(Agente)
                .where(Agente.usuario_id == usuario_id, Agente.tipo == TipoAgente.SORA)
            )
        assert total == 1


async def test_bloco_2_grupo_tem_sora_chefe_e_mensagem_com_anexo(mundo: Mundo) -> None:  # noqa: F811
    email = f"etapa5-bloco2-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        sora = (await cliente.get("/v1/agentes/sora", headers=auth)).json()
        bots = []
        for nome, cor in (("Lume", "#56A8FF"), ("Nexo", "#46E8A8")):
            resposta = await cliente.post(
                "/v1/agentes",
                headers=auth,
                json={
                    "nome": nome,
                    "funcao": "Pesquisa",
                    "papel": "pesquisador",
                    "cor": cor,
                    "ferramentas": ["buscar_web"],
                },
            )
            assert resposta.status_code == 201, resposta.text
            bots.append(resposta.json())

        criado = await cliente.post(
            "/v1/grupos",
            headers=auth,
            json={
                "nome": "Lançamento",
                "membros": [bot["id"] for bot in bots],
                "proposito": "Preparar lançamento",
            },
        )
        assert criado.status_code == 201, criado.text
        grupo = criado.json()
        assert grupo["lider_id"] == sora["id"]
        assert grupo["membros"][0] == sora["id"]
        assert set(grupo["membros"][1:]) == {bot["id"] for bot in bots}
        assert grupo["estado"] == "livre"

        invalido = await cliente.post(
            "/v1/grupos",
            headers=auth,
            json={"nome": "Inválido", "membros": [sora["id"], bots[0]["id"]]},
        )
        assert invalido.status_code == 422

        editado = await cliente.patch(
            f"/v1/grupos/{grupo['id']}", headers=auth, json={"nome": "Equipe de lançamento"}
        )
        assert editado.status_code == 200, editado.text
        assert editado.json()["nome"] == "Equipe de lançamento"
        assert editado.json()["lider_id"] == sora["id"]

        arquivo = await cliente.post(
            "/v1/anexos",
            headers=auth,
            files={"arquivo": ("briefing.txt", b"conteudo", "text/plain")},
        )
        assert arquivo.status_code == 201, arquivo.text
        mensagem = await cliente.post(
            f"/v1/canais-equipe/{grupo['id']}/mensagens",
            headers=auth,
            json={
                "texto": "Use este briefing.",
                "destinatario": bots[0]["id"],
                "anexos": [arquivo.json()["anexo_id"]],
            },
        )
        assert mensagem.status_code == 202, mensagem.text
        assert mensagem.json()["anexos"] == [arquivo.json()["anexo_id"]]

        parada = await cliente.post(
            f"/v1/grupos/{grupo['id']}/membros/{bots[0]['id']}/parar", headers=auth
        )
        assert parada.status_code == 200, parada.text
        assert parada.json() and all(tarefa["status"] == "parada" for tarefa in parada.json())
        repetida = await cliente.post(
            f"/v1/grupos/{grupo['id']}/membros/{bots[0]['id']}/parar", headers=auth
        )
        assert repetida.status_code == 200 and repetida.json() == []
        sora_nao_para = await cliente.post(
            f"/v1/grupos/{grupo['id']}/membros/{sora['id']}/parar", headers=auth
        )
        assert sora_nao_para.status_code == 409

        lista = await cliente.get("/v1/grupos", headers=auth)
        assert lista.status_code == 200
        assert any(item["id"] == grupo["id"] for item in lista.json())


async def test_bloco_3_atencao_estado_decisoes_e_sse(mundo: Mundo) -> None:  # noqa: F811
    await mundo.iniciar_worker()
    email = f"etapa5-bloco3-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        assert (await cliente.get("/v1/agentes/sora", headers=auth)).status_code == 200
        bots = []
        for descricao in ("Pesquisa", "Redação"):
            resposta = await cliente.post(
                "/v1/agentes", headers=auth, json={"descricao": descricao}
            )
            assert resposta.status_code == 201
            bots.append(resposta.json())
        grupo = (
            await cliente.post(
                "/v1/grupos",
                headers=auth,
                json={"nome": "Atenção", "membros": [bot["id"] for bot in bots]},
            )
        ).json()

        async with mundo.fabrica() as sessao:
            usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
            conversa = Conversa(
                usuario_id=usuario_id,
                agente_id=bots[0]["id"],
                tipo=TipoConversa.AGENTE,
            )
            sessao.add(conversa)
            await sessao.flush()
            pergunta = Pergunta(
                conversa_id=conversa.id,
                grupo_id=grupo["id"],
                texto="Qual formato você prefere?",
                opcoes=[{"rotulo": "PDF", "valor": "pdf"}],
                resposta_livre=False,
            )
            aprovacao = Aprovacao(
                usuario_id=usuario_id,
                agente_id=bots[0]["id"],
                grupo_id=grupo["id"],
                acao={"tipo": "rascunho_envio", "ferramenta": "enviar", "resumo": "Enviar?"},
                avaliacao={"motivo": "Envia uma mensagem externa."},
                status=StatusAprovacao.PENDENTE,
                expira_em=datetime.now(UTC) + timedelta(minutes=10),
            )
            sessao.add_all([pergunta, aprovacao])
            await sessao.commit()
            pergunta_id, aprovacao_id = pergunta.id, aprovacao.id

        pedidos = await cliente.get("/v1/atencao", headers=auth)
        assert pedidos.status_code == 200, pedidos.text
        assert {pedido["tipo"] for pedido in pedidos.json()} == {"pergunta", "rascunho_envio"}
        assert all(pedido["grupo_id"] == grupo["id"] for pedido in pedidos.json())
        agente = next(
            item
            for item in (await cliente.get("/v1/agentes", headers=auth)).json()
            if item["id"] == bots[0]["id"]
        )
        assert agente["estado"] == "precisa_de_voce"
        grupo_atual = next(
            item
            for item in (await cliente.get("/v1/grupos", headers=auth)).json()
            if item["id"] == grupo["id"]
        )
        assert grupo_atual["estado"] == "precisa_de_voce"

        decidiu = await cliente.post(
            f"/v1/aprovacoes/{aprovacao_id}/decidir",
            headers=auth,
            json={"decisao": "permitir"},
        )
        assert decidiu.status_code == 204, decidiu.text
        respondeu = await cliente.post(
            f"/v1/perguntas/{pergunta_id}/responder",
            headers=auth,
            json={"valor": "pdf"},
        )
        assert respondeu.status_code == 204, respondeu.text
        assert (await cliente.get("/v1/atencao", headers=auth)).json() == []

        redis = Redis.from_url(mundo.url_redis)
        try:
            eventos = await redis.xrevrange(canal_usuario(usuario_id), count=20)
        finally:
            await redis.aclose()
        nomes = {
            (campos.get(b"event") or campos.get("event")).decode()
            if isinstance(campos.get(b"event") or campos.get("event"), bytes)
            else campos.get(b"event") or campos.get("event")
            for _, campos in eventos
        }
        assert "precisa_de_voce.atualizado" in nomes


async def test_bloco_4_rascunho_so_cria_bot_ao_confirmar(mundo: Mundo) -> None:  # noqa: F811
    await mundo.iniciar_worker()
    email = f"etapa5-bloco4-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        antes = (await cliente.get("/v1/agentes", headers=auth)).json()
        criado = await cliente.post(
            "/v1/bots/rascunhos",
            headers=auth,
            json={"descricao": "Pesquisa notícias e prepara um resumo diário."},
        )
        assert criado.status_code == 201, criado.text
        rascunho = criado.json()
        assert rascunho["status"] == "rascunho"
        assert len((await cliente.get("/v1/agentes", headers=auth)).json()) == len(antes)

        confirmado = await cliente.post(
            f"/v1/bots/rascunhos/{rascunho['id']}/confirmar",
            headers=auth,
            json={
                "nome": "Farol",
                "funcao": "Pesquisa de notícias",
                "rotina": {
                    "descricao": "Preparar o resumo diário",
                    "agendamento": "0 9 * * 1-5",
                    "fuso": "America/Sao_Paulo",
                },
            },
        )
        assert confirmado.status_code == 201, confirmado.text
        bot = confirmado.json()
        assert bot["nome"] == "Farol"
        repetido = await cliente.post(
            f"/v1/bots/rascunhos/{rascunho['id']}/confirmar", headers=auth, json={}
        )
        assert repetido.status_code == 409

        outro = (
            await cliente.post("/v1/bots/rascunhos", headers=auth, json={"descricao": "Outro bot"})
        ).json()
        descartado = await cliente.delete(f"/v1/bots/rascunhos/{outro['id']}", headers=auth)
        assert descartado.status_code == 204
        async with mundo.fabrica() as sessao:
            usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
            rotina = await sessao.scalar(
                select(Rotina).where(
                    Rotina.usuario_id == usuario_id, Rotina.agente_id == UUID(bot["id"])
                )
            )
            assert rotina is not None and rotina.expressao == "0 9 * * 1-5"
            linhas = list(
                await sessao.scalars(
                    select(RascunhoBot).where(RascunhoBot.usuario_id == usuario_id)
                )
            )
            assert {linha.status for linha in linhas} == {"confirmado", "descartado"}


async def test_bloco_5_proposta_aceita_e_recusada_e_sem_publicar(mundo: Mundo) -> None:  # noqa: F811
    await mundo.iniciar_worker()
    email = f"etapa5-bloco5-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        proposta_resp = await cliente.post(
            "/v1/grupos/propostas",
            headers=auth,
            json={"pedido": "Preparar o lançamento de um produto"},
        )
        assert proposta_resp.status_code == 201, proposta_resp.text
        proposta = proposta_resp.json()
        assert proposta["status"] == "proposta"
        assert len(proposta["bots_novos"]) == 2
        assert proposta["bots_reaproveitados"] == []
        # Recarga: a proposta volta pelo GET; os bots novos dela não viram cartões soltos.
        pendentes = (await cliente.get("/v1/grupos/propostas", headers=auth)).json()
        assert [item["id"] for item in pendentes] == [proposta["id"]]
        assert (await cliente.get("/v1/bots/rascunhos", headers=auth)).json() == []
        sozinho = await cliente.post(
            f"/v1/bots/rascunhos/{proposta['bots_novos'][0]['id']}/confirmar",
            headers=auth,
            json={},
        )
        assert sozinho.status_code == 409, sozinho.text
        agentes_antes = (await cliente.get("/v1/agentes", headers=auth)).json()
        assert len([agente for agente in agentes_antes if agente["tipo"] == "individual"]) == 0

        aceitar = await cliente.post(f"/v1/grupos/propostas/{proposta['id']}/aceitar", headers=auth)
        assert aceitar.status_code == 201, aceitar.text
        grupo = aceitar.json()
        assert len(grupo["membros"]) == 3
        mensagens = await cliente.get(f"/v1/canais-equipe/{grupo['id']}/mensagens", headers=auth)
        assert mensagens.status_code == 200
        assert mensagens.json()[0]["texto"] == "Preparar o lançamento de um produto"
        bots = [
            agente
            for agente in (await cliente.get("/v1/agentes", headers=auth)).json()
            if agente["tipo"] == "individual"
        ]
        assert len(bots) == 2

        from app.ferramentas.base import ContextoFerramenta
        from app.ferramentas.propor_grupo import ProporGrupo, propor_grupo

        sora = (await cliente.get("/v1/agentes/sora", headers=auth)).json()
        async with mundo.fabrica() as sessao:
            uid = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
        resultado = await propor_grupo(
            ProporGrupo(pedido="Resuma a campanha em uma frase.", grupo_existente=grupo["nome"]),
            ContextoFerramenta(
                usuario_id=uid, agente_id=UUID(sora["id"]), conversa_id=UUID(grupo["id"])
            ),
        )
        assert "grupo existente" in resultado
        mensagens = (
            await cliente.get(f"/v1/canais-equipe/{grupo['id']}/mensagens", headers=auth)
        ).json()
        assert any(m["texto"] == "Resuma a campanha em uma frase." for m in mensagens)
        assert len((await cliente.get("/v1/grupos", headers=auth)).json()) == 1

        segunda = (
            await cliente.post(
                "/v1/grupos/propostas",
                headers=auth,
                json={"pedido": "Outra iniciativa"},
            )
        ).json()
        recusada = await cliente.post(f"/v1/grupos/propostas/{segunda['id']}/recusar", headers=auth)
        assert recusada.status_code == 204
        assert (await cliente.get("/v1/grupos/propostas", headers=auth)).json() == []
        publicar = await cliente.post(
            f"/v1/conversas/{uuid4()}/aprovar", headers=auth, json={"versao": 1}
        )
        assert publicar.status_code == 404

        async with mundo.fabrica() as sessao:
            usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
            propostas = list(
                await sessao.scalars(
                    select(PropostaGrupo).where(PropostaGrupo.usuario_id == usuario_id)
                )
            )
            assert {item.status for item in propostas} == {"aceita", "recusada"}
            assert (
                await sessao.scalar(
                    select(func.count())
                    .select_from(CanalEquipe)
                    .where(CanalEquipe.usuario_id == usuario_id)
                )
            ) == 1
            assert (
                await sessao.scalar(
                    select(Mensagem.id).where(
                        Mensagem.conteudo == "Preparar o lançamento de um produto"
                    )
                )
                is None
            )


async def _criar_bots_e_grupo(cliente, auth, nomes=("Lume", "Nexo")):
    bots = []
    for nome, cor in zip(nomes, ("#56A8FF", "#46E8A8"), strict=False):
        resposta = await cliente.post(
            "/v1/agentes",
            headers=auth,
            json={
                "nome": nome,
                "funcao": "Pesquisa",
                "papel": "pesquisador",
                "cor": cor,
                "ferramentas": ["buscar_web"],
            },
        )
        assert resposta.status_code == 201, resposta.text
        bots.append(resposta.json())
    grupo = await cliente.post(
        "/v1/grupos", headers=auth, json={"nome": "Equipe", "membros": [b["id"] for b in bots]}
    )
    assert grupo.status_code == 201, grupo.text
    return bots, grupo.json()


async def _tarefas(cliente, auth, grupo_id):
    resposta = await cliente.get(f"/v1/canais-equipe/{grupo_id}/tarefas", headers=auth)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


async def _esperar(condicao, limite_s: float = 30):
    for _ in range(int(limite_s / 0.2)):
        valor = await condicao()
        if valor:
            return valor
        await asyncio.sleep(0.2)
    raise AssertionError("condição não chegou a tempo")


async def test_cartao_no_turno_de_grupo_pausa_e_a_decisao_retoma_o_mesmo_turno(
    mundo: Mundo,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langgraph.types import Interrupt

    chamadas: list[dict] = []
    alvo: dict[str, UUID] = {}

    async def turno_falso(*, contexto, modelos, checkpointer, entrada=None, resposta=None, **_):
        chamadas.append(
            {
                "agente": str(contexto.agente_id),
                "thread": contexto.thread_proprio,
                "resposta": resposta,
                "extras": list(contexto.ferramentas_extras),
            }
        )
        if resposta is not None or contexto.agente_id != alvo.get("id"):
            from langchain_core.messages import AIMessage

            return {"messages": [AIMessage(content="Relatório concluído.")]}
        # Como o revisor faz: o cartão é gravado antes da interrupção.
        async with mundo.fabrica() as sessao:
            cartao = Aprovacao(
                usuario_id=contexto.usuario_id,
                agente_id=contexto.agente_id,
                grupo_id=contexto.canal_id,
                acao={"ferramenta": "enviar_email", "argumentos": {"para": "cliente"}},
                avaliacao={"motivo": "Envia um e-mail para fora."},
                status=StatusAprovacao.PENDENTE,
                expira_em=datetime.now(UTC) + timedelta(minutes=10),
            )
            sessao.add(cartao)
            await sessao.commit()
        return {
            "__interrupt__": [
                Interrupt(value={"tipo": "aprovacao", "aprovacao_id": str(cartao.id)})
            ]
        }

    async def sem_modelos(*_args, **_kwargs):
        return []

    monkeypatch.setattr("app.agentes.montar_e_rodar_agente", turno_falso)
    monkeypatch.setattr("workers.equipe.modelo_falso_ativo", lambda: False)
    monkeypatch.setattr("workers.equipe.modelos_do_papel", sem_modelos)
    await mundo.iniciar_worker()

    email = f"etapa5-pausa-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        bots, grupo = await _criar_bots_e_grupo(cliente, auth)
        alvo["id"] = UUID(bots[0]["id"])
        enviada = await cliente.post(
            f"/v1/canais-equipe/{grupo['id']}/mensagens",
            headers=auth,
            json={"texto": "Mande o relatório ao cliente.", "destinatario": bots[0]["id"]},
        )
        assert enviada.status_code == 202, enviada.text

        async def pausada():
            tarefas = await _tarefas(cliente, auth, grupo["id"])
            return [t for t in tarefas if t["motivo"] == "aguardando_decisao"]

        [tarefa] = await _esperar(pausada)
        assert tarefa["status"] == "parada" and tarefa["dono_id"] == bots[0]["id"]
        chamadas[:] = [c for c in chamadas if c["agente"] == bots[0]["id"]]
        assert chamadas[0]["extras"] == ["buscar_web", "ler_pagina", "ler_anexo"]
        pedidos = (await cliente.get("/v1/atencao", headers=auth)).json()
        assert [p["grupo_id"] for p in pedidos] == [grupo["id"]]
        estado = next(
            g
            for g in (await cliente.get("/v1/grupos", headers=auth)).json()
            if g["id"] == grupo["id"]
        )["estado"]
        assert estado == "precisa_de_voce"

        decidiu = await cliente.post(
            f"/v1/aprovacoes/{pedidos[0]['id']}/decidir",
            headers=auth,
            json={"decisao": "permitir"},
        )
        assert decidiu.status_code == 204, decidiu.text

        async def concluida():
            tarefas = await _tarefas(cliente, auth, grupo["id"])
            return [
                t
                for t in tarefas
                if t["tarefa_id"] == tarefa["tarefa_id"] and t["status"] == "concluida"
            ]

        await _esperar(concluida)
        chamadas[:] = [c for c in chamadas if c["agente"] == bots[0]["id"]]
        assert len(chamadas) == 2
        assert chamadas[1]["resposta"] == "permitir_uma_vez"
        assert chamadas[1]["thread"] == chamadas[0]["thread"]
        assert (await cliente.get("/v1/atencao", headers=auth)).json() == []


async def test_bot_apagado_sai_dos_grupos_e_nao_prende_o_estado(mundo: Mundo) -> None:  # noqa: F811
    email = f"etapa5-apagar-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        bots, grupo = await _criar_bots_e_grupo(cliente, auth)
        # Sem worker: a tarefa fica na fila, e o Parar a deixa parada (estado "precisa de você").
        enviada = await cliente.post(
            f"/v1/canais-equipe/{grupo['id']}/mensagens",
            headers=auth,
            json={"texto": "Pesquise preços.", "destinatario": bots[0]["id"]},
        )
        assert enviada.status_code == 202, enviada.text
        parada = await cliente.post(
            f"/v1/grupos/{grupo['id']}/membros/{bots[0]['id']}/parar", headers=auth
        )
        assert parada.status_code == 200 and parada.json(), parada.text

        def do_grupo(lista):
            return next(g for g in lista if g["id"] == grupo["id"])

        antes = do_grupo((await cliente.get("/v1/grupos", headers=auth)).json())
        assert antes["estado"] == "precisa_de_voce"

        apagou = await cliente.delete(f"/v1/agentes/{bots[0]['id']}", headers=auth)
        assert apagou.status_code == 204, apagou.text

        depois = do_grupo((await cliente.get("/v1/grupos", headers=auth)).json())
        assert bots[0]["id"] not in depois["membros"]
        assert depois["estado"] == "livre"
        tarefas = await _tarefas(cliente, auth, grupo["id"])
        assert {t["status"] for t in tarefas if t["dono_id"] == bots[0]["id"]} == {"cancelada"}
        mensagens = (
            await cliente.get(f"/v1/canais-equipe/{grupo['id']}/mensagens", headers=auth)
        ).json()
        textos = [
            m["texto"]
            for m in (
                mensagens.get("mensagens", mensagens) if isinstance(mensagens, dict) else mensagens
            )
        ]
        assert any("Lume foi apagado" in texto for texto in textos)


async def test_gatilhos_do_modelo_falso_abrem_os_cartoes_reais(mundo: Mundo) -> None:  # noqa: F811
    """Para o QA no navegador: ``[grupo]`` na Sora vira proposta; ``[pergunta]`` e
    ``[aprovacao]`` no chat 1:1 do bot viram pergunta e aprovação em /v1/atencao."""
    await mundo.iniciar_worker()
    email = f"etapa5-gatilhos-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        sora = await cliente.post(
            "/v1/conversas", headers=auth, json={"texto": "Lance minha loja online [grupo]"}
        )
        assert sora.status_code == 201, sora.text

        async def proposta():
            return (await cliente.get("/v1/grupos/propostas", headers=auth)).json()

        [pendente] = await _esperar(proposta)
        assert pendente["pedido"] == "Lance minha loja online"
        assert (await cliente.get("/v1/agentes", headers=auth)).json()[0]["tipo"] == "sora"

        bot = (
            await cliente.post("/v1/agentes", headers=auth, json={"descricao": "Resumos"})
        ).json()
        for gatilho, tipo in (("[pergunta]", "pergunta"), ("[aprovacao]", "aprovacao")):
            conversa = await cliente.post(
                "/v1/conversas",
                headers=auth,
                json={"agente_id": bot["id"], "texto": f"Resuma o dia {gatilho}"},
            )
            assert conversa.status_code == 201, conversa.text

            async def cartao(tipo=tipo):
                pedidos = (await cliente.get("/v1/atencao", headers=auth)).json()
                return [p for p in pedidos if p["tipo"] == tipo and p["agente_id"] == bot["id"]]

            await _esperar(cartao)


async def test_sem_teto_de_bots_grupo_de_2_a_5_e_especialista_fica_de_fora(
    mundo: Mundo,  # noqa: F811
) -> None:
    """Decisões 6 e 7 (Heitor, 2026-11-08) e especialista como agente interno."""
    email = f"etapa5-limites-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        bots = []
        for indice in range(7):  # antes o teto era 5
            criado = await cliente.post(
                "/v1/agentes", headers=auth, json={"descricao": f"Ajudante {indice}"}
            )
            assert criado.status_code == 201, criado.text
            bots.append(criado.json()["id"])

        seis = await cliente.post(
            "/v1/grupos", headers=auth, json={"nome": "Grande", "membros": bots[:6]}
        )
        assert seis.status_code == 422
        cinco = await cliente.post(
            "/v1/grupos", headers=auth, json={"nome": "Cheio", "membros": bots[:5]}
        )
        assert cinco.status_code == 201, cinco.text
        assert len(cinco.json()["membros"]) == 6  # Sora + 5 bots

        async with mundo.fabrica() as sessao:
            usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
            especialista = Agente(
                usuario_id=usuario_id,
                tipo=TipoAgente.ESPECIALISTA,
                nome="Pesquisador interno",
                papel="pesquisador",
            )
            sessao.add(especialista)
            await sessao.commit()
            especialista_id = str(especialista.id)

        listados = (await cliente.get("/v1/agentes", headers=auth)).json()
        assert next(a for a in listados if a["id"] == especialista_id)["tipo"] == "especialista"
        com_especialista = await cliente.post(
            "/v1/grupos",
            headers=auth,
            json={"nome": "Misto", "membros": [bots[0], especialista_id]},
        )
        assert com_especialista.status_code == 422

        proposta = (
            await cliente.post("/v1/grupos/propostas", headers=auth, json={"pedido": "Feira"})
        ).json()
        assert all(b["tipo"] == "individual" for b in proposta["bots_reaproveitados"])
        ajuste = await cliente.patch(
            f"/v1/grupos/propostas/{proposta['id']}",
            headers=auth,
            json={"bots_reaproveitados": [bots[0], especialista_id]},
        )
        assert ajuste.status_code == 422
        demais = await cliente.patch(
            f"/v1/grupos/propostas/{proposta['id']}",
            headers=auth,
            json={"bots_reaproveitados": bots[:6], "bots_novos": []},
        )
        assert demais.status_code == 422


async def test_apagar_conversa_ou_bot_fecha_os_pedidos_pendentes(mundo: Mundo) -> None:  # noqa: F811
    """Achado da Vela: pedido de conversa ou bot apagado não pode ficar em /v1/atencao."""
    await mundo.iniciar_worker()
    email = f"etapa5-apagar-pendentes-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        bot = (
            await cliente.post("/v1/agentes", headers=auth, json={"descricao": "Resumos"})
        ).json()
        conversas = {}
        for gatilho, tipo in (("[aprovacao]", "aprovacao"), ("[pergunta]", "pergunta")):
            criada = await cliente.post(
                "/v1/conversas",
                headers=auth,
                json={"agente_id": bot["id"], "texto": f"Resuma o dia {gatilho}"},
            )
            assert criada.status_code == 201, criada.text
            conversas[tipo] = criada.json()["id"]

        async def os_dois():
            pedidos = (await cliente.get("/v1/atencao", headers=auth)).json()
            tipos = {p["tipo"] for p in pedidos if p["agente_id"] == bot["id"]}
            return tipos == {"aprovacao", "pergunta"}

        await _esperar(os_dois)

        async def estado_do_bot():
            lista = (await cliente.get("/v1/agentes", headers=auth)).json()
            return next(a for a in lista if a["id"] == bot["id"])["estado"]

        assert await estado_do_bot() == "precisa_de_voce"

        async with mundo.fabrica() as sessao:
            usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
        redis = Redis.from_url(mundo.url_redis, decode_responses=True)
        try:
            antes = len(await redis.xrange(canal_usuario(usuario_id)))
            apagou = await cliente.delete(f"/v1/conversas/{conversas['aprovacao']}", headers=auth)
            assert apagou.status_code == 204, apagou.text
            pedidos = (await cliente.get("/v1/atencao", headers=auth)).json()
            assert [p["tipo"] for p in pedidos] == ["pergunta"]
            assert await estado_do_bot() == "precisa_de_voce"  # a pergunta continua
            novos = (await redis.xrange(canal_usuario(usuario_id)))[antes:]
            assert any(c.get("event") == "precisa_de_voce.atualizado" for _, c in novos)
        finally:
            await redis.aclose()
        async with mundo.fabrica() as sessao:
            cartao = await sessao.scalar(
                select(Aprovacao).where(Aprovacao.usuario_id == usuario_id)
            )
            assert cartao.status == StatusAprovacao.EXPIRADA

        apagou_bot = await cliente.delete(f"/v1/agentes/{bot['id']}", headers=auth)
        assert apagou_bot.status_code == 204, apagou_bot.text
        assert (await cliente.get("/v1/atencao", headers=auth)).json() == []


async def test_regressoes_propostas_rascunhos_e_grupo_incompleto(mundo: Mundo) -> None:  # noqa: F811
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, f"ancora2-{uuid4()}@exemplo.com")
        pedido = (
            "Quero lançar uma linha de produtos de verão, com campanha, textos e calendário\n"
            "Segunda linha"
        )
        resposta = await cliente.post("/v1/grupos/propostas", headers=auth, json={"pedido": pedido})
        assert resposta.status_code == 201, resposta.text
        proposta = resposta.json()
        assert 1 <= len(proposta["nome"]) <= 60
        assert pedido.startswith(proposta["nome"])
        for nome in ("   ", "x" * 61, ""):
            invalida = await cliente.patch(
                f"/v1/grupos/propostas/{proposta['id']}", headers=auth, json={"nome": nome}
            )
            assert invalida.status_code == 422
            assert invalida.json()["detail"] == "O nome do grupo precisa ter de 1 a 60 caracteres."
        soltos = []
        for _ in range(2):
            r = await cliente.post(
                "/v1/bots/rascunhos", headers=auth, json={"descricao": "Pesquisar fontes"}
            )
            assert r.status_code == 201, r.text
            soltos.append(r.json())
        todos = proposta["bots_novos"] + soltos
        assert len({r["nome"] for r in todos}) == 4
        assert len({r["cor"] for r in todos}) == 4
        # A ferramenta da Sora também pode repetir o nome sugerido pelo modelo.
        from app.rascunhos_bot import criar_rascunho

        async with mundo.fabrica() as sessao:
            dono = await sessao.scalar(
                select(RascunhoBot.usuario_id).where(RascunhoBot.id == UUID(soltos[0]["id"]))
            )
            primeiro = await criar_rascunho(sessao, dono, descricao="Pesquisa", nome="Lume")
            segundo = await criar_rascunho(sessao, dono, descricao="Pesquisa", nome="Lume")
            assert primeiro.dados["nome"] != segundo.dados["nome"]
            assert primeiro.dados["cor"] != segundo.dados["cor"]
            await sessao.commit()
        removido = proposta["bots_novos"][1]["id"]
        ajuste = await cliente.patch(
            f"/v1/grupos/propostas/{proposta['id']}",
            headers=auth,
            json={"bots_novos": [{"id": proposta["bots_novos"][0]["id"]}, {"id": soltos[0]["id"]}]},
        )
        assert ajuste.status_code == 200, ajuste.text
        pendentes = (await cliente.get("/v1/bots/rascunhos", headers=auth)).json()
        assert removido not in {r["id"] for r in pendentes}
        assert (
            await cliente.post(f"/v1/bots/rascunhos/{removido}/confirmar", headers=auth, json={})
        ).status_code == 409
        aceita = await cliente.post(f"/v1/grupos/propostas/{proposta['id']}/aceitar", headers=auth)
        assert aceita.status_code == 201, aceita.text
        grupo = aceita.json()
        assert grupo["precisa_de_bots"] is False
        bots = [b for b in grupo["membros"] if b != grupo["lider_id"]]
        for membros in ([], bots[:1], [str(uuid4()) for _ in range(6)]):
            for metodo, rota in (
                (cliente.post, "/v1/grupos"),
                (cliente.patch, f"/v1/grupos/{grupo['id']}"),
            ):
                invalida = await metodo(
                    rota, headers=auth, json={"nome": "Inválido", "membros": membros}
                )
                assert invalida.status_code == 422
                assert invalida.json()["detail"] == "Escolha de 2 a 5 bots."
        assert (await cliente.delete(f"/v1/agentes/{bots[0]}", headers=auth)).status_code == 204
        grupos = (await cliente.get("/v1/grupos", headers=auth)).json()
        assert grupos[0]["id"] == grupo["id"]
        assert grupos[0]["precisa_de_bots"] is True
        rota = f"/v1/canais-equipe/{grupo['id']}/mensagens"
        bloqueada = await cliente.post(rota, headers=auth, json={"texto": "Continue"})
        assert bloqueada.status_code == 409, bloqueada.text
        assert (
            bloqueada.json()["detail"]
            == "Este grupo precisa de pelo menos 2 bots. Adicione bots para continuar."
        )
        novo = await cliente.post(
            f"/v1/bots/rascunhos/{soltos[1]['id']}/confirmar", headers=auth, json={}
        )
        assert novo.status_code == 201, novo.text
        recuperado = await cliente.patch(
            f"/v1/grupos/{grupo['id']}",
            headers=auth,
            json={"membros": [bots[1], novo.json()["id"]]},
        )
        assert recuperado.status_code == 200, recuperado.text
        assert recuperado.json()["precisa_de_bots"] is False
        assert (
            await cliente.post(rota, headers=auth, json={"texto": "Continue"})
        ).status_code == 202


async def test_grupo_com_429_espera_avisa_no_canal_e_entrega_o_resultado(
    mundo: Mundo,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import litellm
    from langchain_core.messages import AIMessage

    tentativas: list[int] = []

    async def turno_falso(*, contexto, modelos, checkpointer, entrada=None, resposta=None, **_):
        tentativas.append(1)
        if len(tentativas) == 1:
            raise litellm.RateLimitError(
                message="rate limit", llm_provider="groq", model="groq/modelo"
            )
        return {"messages": [AIMessage(content="Haicai: café na manhã.")]}

    async def sem_modelos(*_args, **_kwargs):
        return []

    monkeypatch.setattr("app.agentes.montar_e_rodar_agente", turno_falso)
    monkeypatch.setattr("workers.equipe.modelo_falso_ativo", lambda: False)
    monkeypatch.setattr("workers.equipe.modelos_do_papel", sem_modelos)
    monkeypatch.setattr("app.llm.limite.ESPERA_PADRAO_S", 0.1)
    await mundo.iniciar_worker()

    email = f"etapa5-429-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        bots, grupo = await _criar_bots_e_grupo(cliente, auth)
        enviada = await cliente.post(
            f"/v1/canais-equipe/{grupo['id']}/mensagens",
            headers=auth,
            json={"texto": "Escreva um haicai.", "destinatario": bots[0]["id"]},
        )
        assert enviada.status_code == 202, enviada.text

        async def resultado():
            mensagens = (
                await cliente.get(f"/v1/canais-equipe/{grupo['id']}/mensagens", headers=auth)
            ).json()
            return [m for m in mensagens if m["texto"] == "Haicai: café na manhã."]

        await _esperar(resultado)
        mensagens = (
            await cliente.get(f"/v1/canais-equipe/{grupo['id']}/mensagens", headers=auth)
        ).json()
        assert any("limite" in m["texto"] for m in mensagens)
        assert len(tentativas) == 2


async def test_criar_bot_por_descricao_isolado(mundo: Mundo) -> None:  # noqa: F811
    async with httpx.AsyncClient(base_url=mundo.url, timeout=45) as cliente:
        auth = await entrar(cliente, mundo.fabrica, f"novo-{uuid4()}@exemplo.com")
        outro = await entrar(cliente, mundo.fabrica, f"outro-{uuid4()}@exemplo.com")
        ids = []
        for _ in range(2):
            resposta = await cliente.post(
                "/v1/bots/criar-por-descricao",
                headers=auth,
                json={"descricao": "entre no site https://exemplo.com e compare produtos"},
            )
            assert resposta.status_code == 201, resposta.text
            bot = resposta.json()
            assert bot["cor"] != "#E2ECFF"
            assert "navegador_abrir" in bot["ferramentas"]
            assert "ler_pagina" in bot["ferramentas"]
            ids.append(bot["id"])
        lista = (await cliente.get("/v1/agentes", headers=auth)).json()
        criados = [b for b in lista if b["id"] in ids]
        assert len({b["nome"] for b in criados}) == 2
        assert len({b["cor"] for b in criados}) == 2
        assert (await cliente.get("/v1/bots/rascunhos", headers=auth)).json() == []
        outros = (await cliente.get("/v1/agentes", headers=outro)).json()
        assert not any(b["id"] in ids for b in outros)
        for descricao in ("", "   ", "x" * 2001):
            assert (
                await cliente.post(
                    "/v1/bots/criar-por-descricao", headers=auth, json={"descricao": descricao}
                )
            ).status_code == 422
