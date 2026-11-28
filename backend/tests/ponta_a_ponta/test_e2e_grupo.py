"""A Sora sintetiza uma vez quando os bots do @todos terminam."""

import asyncio

import pytest

from tests.ponta_a_ponta.http import sql

pytestmark = [pytest.mark.integracao, pytest.mark.asyncio]


async def _bot(cliente, nome, cor, instrucoes):
    rascunho = await cliente.post("/v1/bots/rascunhos", json={"descricao": f"Bot {nome}"})
    assert rascunho.status_code == 201, rascunho.text
    confirmado = await cliente.post(
        f"/v1/bots/rascunhos/{rascunho.json()['id']}/confirmar",
        json={
            "nome": nome,
            "funcao": "Pesquisa",
            "instrucoes": instrucoes,
            "cor": cor,
            "ferramentas": [],
        },
    )
    assert confirmado.status_code == 201, confirmado.text
    return confirmado.json()["id"]


async def _tarefas_terminadas(cliente, rota, revisao_minima=0):
    async with asyncio.timeout(30):
        while True:
            resposta = await cliente.get(f"{rota}/tarefas")
            assert resposta.status_code == 200, resposta.text
            tarefas = resposta.json()
            if (
                len(tarefas) == 3
                and all(t["status"] in {"concluida", "falhou"} for t in tarefas)
                and max(t["revisao"] for t in tarefas) >= revisao_minima
            ):
                return tarefas
            await asyncio.sleep(0.2)


async def test_atodos_com_falha_parcial_publica_uma_sintese(cliente_e2e, mundo):
    atlas = await _bot(cliente_e2e, "Atlas", "#56A8FF", "Pesquisa fontes.")
    luna = await _bot(cliente_e2e, "Luna", "#AC80FF", "Organiza as referências.")
    nina = await _bot(cliente_e2e, "Nina", "#46E8A8", "[falha_bot]")
    grupo = await cliente_e2e.post(
        "/v1/grupos", json={"nome": "Pesquisa", "membros": [atlas, luna, nina]}
    )
    assert grupo.status_code == 201, grupo.text
    dados = grupo.json()
    sora = dados["lider_id"]
    rota = f"/v1/canais-equipe/{dados['id']}"
    pedido = await cliente_e2e.post(
        f"{rota}/mensagens", json={"texto": "@todos tragam uma contribuição [falha_bot]"}
    )
    assert pedido.status_code == 202, pedido.text
    pedido_id = pedido.json()["mensagem_id"]
    await mundo.iniciar_worker()

    tarefas = await _tarefas_terminadas(cliente_e2e, rota)
    assert {t["dono_id"]: t["status"] for t in tarefas} == {
        atlas: "concluida",
        luna: "concluida",
        nina: "falhou",
    }

    async def conferir_sintese():
        historico = await cliente_e2e.get(f"{rota}/mensagens")
        assert historico.status_code == 200, historico.text
        respostas = [m for m in historico.json() if m["responde_a"] == pedido_id]
        sinteses = [m for m in respostas if m["agente_id"] == sora]
        assert len(sinteses) == 1
        sintese = sinteses[0]
        assert sintese["tipo"] == "mensagem"
        entregas = [m for m in respostas if m["agente_id"] in {atlas, luna}]
        assert {m["agente_id"] for m in entregas if m["tipo"] == "resultado"} == {atlas, luna}
        assert all(m["texto"] in sintese["texto"] for m in entregas)
        for trecho in ("**Atlas** entregou", "**Luna** entregou", "**Nina** falhou"):
            assert trecho in sintese["texto"]
        return sintese["mensagem_id"]

    sintese_id = await conferir_sintese()
    falha = next(t for t in tarefas if t["dono_id"] == nina)
    reaberta = await cliente_e2e.post(f"/v1/tarefas-canal/{falha['tarefa_id']}/retomar")
    assert reaberta.status_code == 200, reaberta.text
    tarefas = await _tarefas_terminadas(cliente_e2e, rota, falha["revisao"] + 1)
    assert next(t["status"] for t in tarefas if t["dono_id"] == nina) == "falhou"
    assert await conferir_sintese() == sintese_id
    contagem = await sql(
        mundo,
        """
        select count(*) as total from mensagens_canal
        where responde_a = :pedido and agente_id = :sora
        """,
        pedido=pedido_id,
        sora=sora,
    )
    assert contagem[0].total == 1


async def test_atodos_avisa_quando_todos_os_bots_estao_pausados(cliente_e2e):
    atlas = await _bot(cliente_e2e, "Atlas", "#56A8FF", "Pesquisa fontes.")
    luna = await _bot(cliente_e2e, "Luna", "#AC80FF", "Organiza as referências.")
    grupo = await cliente_e2e.post(
        "/v1/grupos", json={"nome": "Pesquisa", "membros": [atlas, luna]}
    )
    assert grupo.status_code == 201, grupo.text
    for bot in (atlas, luna):
        pausa = await cliente_e2e.post(f"/v1/agentes/{bot}/fila/pausar")
        assert pausa.status_code == 200, pausa.text
        assert pausa.json()["pausada"] is True

    rota = f"/v1/canais-equipe/{grupo.json()['id']}"
    texto = "@todos tragam uma contribuição"
    pedido = await cliente_e2e.post(f"{rota}/mensagens", json={"texto": texto})
    assert pedido.status_code == 202, pedido.text
    historico = await cliente_e2e.get(f"{rota}/mensagens")
    assert historico.status_code == 200, historico.text
    assert [mensagem["texto"] for mensagem in historico.json()] == [
        texto,
        "Nenhum bot do grupo pode receber trabalho agora.",
    ]
    tarefas = await cliente_e2e.get(f"{rota}/tarefas")
    assert tarefas.status_code == 200, tarefas.text
    assert tarefas.json() == []


async def test_apagar_ultimo_bot_com_tarefa_aberta_publica_sintese(cliente_e2e, mundo):
    atlas = await _bot(cliente_e2e, "Atlas", "#56A8FF", "Pesquisa fontes.")
    luna = await _bot(cliente_e2e, "Luna", "#AC80FF", "Organiza as referências.")
    nina = await _bot(cliente_e2e, "Nina", "#46E8A8", "Redige o resumo.")
    grupo = await cliente_e2e.post(
        "/v1/grupos", json={"nome": "Pesquisa", "membros": [atlas, luna, nina]}
    )
    assert grupo.status_code == 201, grupo.text
    sora = grupo.json()["lider_id"]
    rota = f"/v1/canais-equipe/{grupo.json()['id']}"
    pedido = await cliente_e2e.post(
        f"{rota}/mensagens", json={"texto": "@todos tragam uma contribuição"}
    )
    assert pedido.status_code == 202, pedido.text
    pedido_id = pedido.json()["mensagem_id"]

    tarefas = await cliente_e2e.get(f"{rota}/tarefas")
    assert tarefas.status_code == 200, tarefas.text
    tarefa_nina = next(tarefa for tarefa in tarefas.json() if tarefa["dono_id"] == nina)
    pausa = await cliente_e2e.post(f"/v1/tarefas-canal/{tarefa_nina['tarefa_id']}/parar")
    assert pausa.status_code == 200, pausa.text
    await mundo.iniciar_worker()

    esperadas = {atlas: "concluida", luna: "concluida", nina: "parada"}
    async with asyncio.timeout(30):
        while True:
            tarefas = await cliente_e2e.get(f"{rota}/tarefas")
            assert tarefas.status_code == 200, tarefas.text
            if {tarefa["dono_id"]: tarefa["status"] for tarefa in tarefas.json()} == esperadas:
                break
            await asyncio.sleep(0.2)

    async def sinteses():
        historico = await cliente_e2e.get(f"{rota}/mensagens")
        assert historico.status_code == 200, historico.text
        return [
            m for m in historico.json() if m["responde_a"] == pedido_id and m["agente_id"] == sora
        ]

    assert await sinteses() == []
    apagar = await cliente_e2e.delete(f"/v1/agentes/{nina}")
    assert apagar.status_code == 204, apagar.text
    [sintese] = await sinteses()
    assert sintese["tipo"] == "mensagem"
    for trecho in (
        "**Atlas** entregou",
        "**Luna** entregou",
        "**Nina** saiu do grupo e teve a tarefa cancelada.",
    ):
        assert trecho in sintese["texto"]
