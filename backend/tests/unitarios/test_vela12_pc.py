"""Vela-12: o controle do PC (C3) fazendo de verdade uma tarefa simples (Excel).

Teste real (2026-11-15): "Café\\t2\\t10,50\\n" era recusado como senha (a linha inteira contava
como uma palavra só), então nenhuma tabela com preço passava.
"""

from __future__ import annotations

import pytest

from app.computador.interface import parece_senha


@pytest.mark.parametrize(
    "linha",
    [
        "Produto\tQuantidade\tPreço\n",
        "Café\t2\t10,50\n",
        "Pão de queijo\t6\t0,80\n",
        "Leite\t3\t5,20",
        "Total\t=B2*C2\n",
        "Ana Souza\tana@empresa.com.br\t(11) 91234-5678\n",
    ],
)
def test_linha_de_planilha_nao_e_senha(linha: str) -> None:
    assert not parece_senha(linha)


@pytest.mark.parametrize(
    "linha",
    [
        "login\tS3nh@Forte!\n",  # a célula com cara de senha continua recusada
        "Abc123!@#\tqualquer\n",
        "conta\tusuario\nXy7#kq9!Lm\n",
        "token\tsk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789\n",
    ],
)
def test_celula_com_cara_de_senha_continua_recusada(linha: str) -> None:
    assert parece_senha(linha)


# ---------- não dizer que fez sem conferir (app/computador/conferencia.py) ----------

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402

from app.computador.conferencia import (  # noqa: E402
    AVISO,
    acoes_do_turno,
    afirma_que_fez,
    precisa_de_aviso,
    texto_com_aviso,
)


def _turno(*resultados: str, alvo: str = "pc_usuario") -> list:
    mensagens: list = [HumanMessage("abre o excel e monta uma tabela")]
    for i, conteudo in enumerate(resultados):
        mensagens.append(
            AIMessage(
                "",
                tool_calls=[
                    {
                        "name": "computador_agir",
                        "args": {"alvo": alvo, "acoes": [{"tipo": "tecla", "tecla": "Escape"}]},
                        "id": f"c{i}",
                    }
                ],
            )
        )
        mensagens.append(ToolMessage(conteudo, tool_call_id=f"c{i}", name="computador_agir"))
    return mensagens


def test_turno_sem_acao_conferida_ganha_aviso() -> None:
    erro = "Erro: A captura foi ocultada: um programa bloqueado está na frente. Peça ao usuário."
    acoes = acoes_do_turno(_turno(erro))
    assert acoes.tentativas == 1 and acoes.conferidas == 0
    assert precisa_de_aviso("Pronto! Criei a tabela no Excel.", acoes)
    texto = texto_com_aviso("Pronto! Criei a tabela no Excel.", acoes)
    assert texto.startswith(AVISO)
    assert "A captura foi ocultada" in texto and "Criei" not in texto


def test_turno_com_acao_conferida_fica_como_esta() -> None:
    ok = "1 de 1 ação(ões) feita(s). Conferência: a tela mudou depois da ação.\n\nComputador…"
    acoes = acoes_do_turno(_turno("Erro: falhou", ok))
    assert acoes.conferidas == 1
    assert not precisa_de_aviso("Pronto! Criei a tabela no Excel.", acoes)


def test_tela_que_nao_mudou_nao_conta_como_conferida() -> None:
    nao_mudou = "1 de 1 ação(ões) feita(s). Conferência: a tela NÃO mudou. A ação pode não ter tido"
    assert acoes_do_turno(_turno(nao_mudou)).conferidas == 0


def test_dizer_que_fez_sem_nem_tentar_tambem_ganha_aviso() -> None:
    acoes = acoes_do_turno([HumanMessage("abre o excel")])
    assert precisa_de_aviso("Prontinho, abri o Excel e preenchi a planilha.", acoes)
    assert "Não cheguei a usar o computador" in texto_com_aviso("Abri o Excel.", acoes)
    # conversa que não fala do computador não é mexida
    assert not precisa_de_aviso("Pronto, aqui está o resumo que você pediu.", acoes)


def test_quem_ja_admite_que_nao_conseguiu_nao_e_mexido() -> None:
    acoes = acoes_do_turno(_turno("Erro: o PC está em uso por Atlas."))
    for texto in [
        "Não consegui abrir o Excel: o computador está em uso.",
        "Pedi permissão para usar o Excel; aguardando você no cartão.",
        "Vou abrir o Excel agora.",
    ]:
        assert not precisa_de_aviso(texto, acoes), texto
    assert afirma_que_fez("Está pronta a tabela.")


def test_acoes_no_computador_virtual_nao_contam() -> None:
    acoes = acoes_do_turno(_turno("Erro: falhou", alvo="virtual"))
    assert acoes.tentativas == 0


# ---------- o middleware ----------


async def test_middleware_troca_a_resposta_final_e_o_falar(monkeypatch) -> None:
    from uuid import uuid4

    from app.agentes.middleware import conferencia_pc
    from app.agentes.middleware.conferencia_pc import MiddlewareConferenciaPc

    soltou: list = []

    async def soltar(usuario_id, agente_id) -> None:
        soltou.append((usuario_id, agente_id))

    monkeypatch.setattr(conferencia_pc, "soltar_o_pc", soltar)
    m = MiddlewareConferenciaPc(uuid4(), uuid4())
    mensagens = [*_turno("Erro: A janela sumiu."), AIMessage("Pronto! Tabela criada.", id="fim")]
    saida = await m.aafter_model({"messages": mensagens}, None)
    assert saida is not None
    nova = saida["messages"][0]
    assert nova.id == "fim" and nova.content.startswith(AVISO)

    class Pedido:
        def __init__(self) -> None:
            self.tool_call = {
                "name": "falar",
                "args": {"texto": "Pronto! Abri o Excel."},
                "id": "f",
            }
            self.state = {"messages": mensagens[:-1]}

    pedido = Pedido()

    async def handler(req):
        return req.tool_call["args"]["texto"]

    assert (await m.awrap_tool_call(pedido, handler)).startswith(AVISO)
    await m.aafter_agent({"messages": mensagens}, None)
    assert len(soltou) == 1
