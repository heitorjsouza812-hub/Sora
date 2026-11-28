"""O chat avisa quando a reserva responde e respeita uma escolha sem reserva."""

import pytest

from tests.ponta_a_ponta.http import criar_conversa, estado_final_da_fila, ler_ate, sql

pytestmark = [pytest.mark.integracao, pytest.mark.asyncio]

AVISO = "Continuei com outro modelo de IA."


def _fim(evento):
    return evento.nome == "mensagem.fim"


def _avisos(eventos):
    return [
        evento
        for evento in eventos
        if evento.nome == "passo"
        and (evento.dados.get("resultado") or {}).get("aviso") == "troca_de_modelo"
    ]


def _resposta(eventos):
    return "".join(evento.dados["texto"] for evento in eventos if evento.nome == "mensagem.delta")


@pytest.mark.parametrize("falha", ["timeout", "500"])
async def test_reserva_responde_com_um_aviso(cliente_e2e, mundo, falha):
    await mundo.iniciar_worker()
    conversa = await criar_conversa(cliente_e2e, f"Responda ao pedido [falha_provedor:{falha}]")
    eventos = await ler_ate(cliente_e2e, conversa, _fim)
    avisos = _avisos(eventos)
    assert len(avisos) == 1
    assert avisos[0].dados["texto"] == AVISO
    assert avisos[0].dados["status"] == "concluido"
    assert "resposta de exemplo" in _resposta(eventos)


@pytest.mark.parametrize("com_bot", [False, True], ids=["sora", "bot"])
async def test_duas_respostas_da_reserva_no_mesmo_turno_emitem_um_aviso(
    cliente_e2e, mundo, com_bot
):
    await mundo.iniciar_worker()
    dados = {"texto": "Responda ao pedido [falha_provedor:500] [duas_falas]"}
    if com_bot:
        bot = await cliente_e2e.post(
            "/v1/agentes", json={"descricao": "Bot para responder dúvidas."}
        )
        assert bot.status_code == 201, bot.text
        dados["agente_id"] = bot.json()["id"]
    criada = await cliente_e2e.post("/v1/conversas", json=dados)
    assert criada.status_code == 201, criada.text
    conversa = criada.json()["id"]
    primeira = await ler_ate(cliente_e2e, conversa, _fim)
    segunda = await ler_ate(cliente_e2e, conversa, _fim, cursor=primeira[-1].id)
    assert _resposta(primeira) == "Vou preparar a resposta."
    assert "resposta de exemplo" in _resposta(segunda)
    assert primeira[-1].dados["mensagem_id"] != segunda[-1].dados["mensagem_id"]
    [aviso] = _avisos(primeira + segunda)
    assert aviso.dados["texto"] == AVISO
    assert aviso.dados["agente_id"] == criada.json()["agente_id"]
    assert aviso in primeira
    assert await estado_final_da_fila(mundo, conversa) == "concluido"


async def test_modelo_fixo_sem_reserva_falha_com_aviso_claro(cliente_e2e, mundo):
    await mundo.iniciar_worker()
    conversa = await criar_conversa(cliente_e2e, "Olá, Sora!")
    anteriores = await ler_ate(cliente_e2e, conversa, _fim)
    conexao = await sql(
        mundo,
        """
        select p.id, m.modelo from provedores p
        join modelos_disponiveis m on m.provedor_id = p.id
        join conversas c on c.usuario_id = p.usuario_id
        where c.id = :id
        """,
        id=conversa,
    )
    modelo = conexao[0].modelo
    ajuste = await cliente_e2e.patch(
        f"/v1/conversas/{conversa}/preferencias",
        json={"provedor_id": str(conexao[0].id), "modelo": modelo},
    )
    assert ajuste.status_code == 200, ajuste.text
    enviado = await cliente_e2e.post(
        f"/v1/conversas/{conversa}/mensagens",
        json={"texto": "Responda ao pedido [falha_provedor:500]"},
    )
    assert enviado.status_code == 202, enviado.text
    eventos = await ler_ate(cliente_e2e, conversa, _fim, cursor=anteriores[-1].id)
    assert not _avisos(eventos)
    assert f"O modelo {modelo}, escolhido para esta conversa, está fora do ar" in _resposta(eventos)
