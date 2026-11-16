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


# ---------- cartão pausa o turno e "Permitir" retoma (pc_usuario.py) ----------

from uuid import UUID, uuid4  # noqa: E402

from app.computador import pc_usuario as modulo_pc  # noqa: E402
from app.computador.pc_usuario import NAO_ABRIVEL, PAUSOU_NO_MEIO  # noqa: E402
from app.computador.pc_usuario_canal import CanalPc  # noqa: E402
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta  # noqa: E402
from tests.unitarios.test_pc_usuario import (  # noqa: E402
    AppFalso,
    CartoesFalsos,
    _conectar,
    _erro,
    _observacao,
    _ok,
    _pc,
    _resolvida,
)


class CartoesComTurno(CartoesFalsos):
    def __init__(self) -> None:
        super().__init__()
        self.vinculados: list[tuple[UUID, UUID]] = []

    async def vincular(self, usuario_id, aprovacao_id, *, conversa_id, etapa_id, grupo_id):
        from datetime import UTC, datetime, timedelta

        if self.situacao.get(aprovacao_id) != "pendente":
            return None
        self.vinculados.append((aprovacao_id, conversa_id))
        return datetime.now(UTC) + timedelta(minutes=10)


class TurnoPausado(Exception):
    def __init__(self, valor: dict) -> None:
        super().__init__(valor)
        self.valor = valor


@pytest.fixture
def redis():
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def pausa_do_turno(monkeypatch):
    """Faz o ``interrupt`` do LangGraph virar uma exceção que o teste pega (o turno pausou)."""

    def interromper(valor: dict) -> None:
        raise TurnoPausado(valor)

    monkeypatch.setattr(modulo_pc, "_interromper", interromper)

    async def sem_agendar(*_: object) -> None:
        return None

    import app.ferramentas.criar_agente as criar_agente

    monkeypatch.setattr(criar_agente, "_agendar_expiracao", sem_agendar)


def _contexto(usuario_id: UUID, bot: UUID) -> ContextoFerramenta:
    return ContextoFerramenta(usuario_id=usuario_id, agente_id=bot, conversa_id=uuid4())


async def test_pausa_cartao_permitir_retoma_o_mesmo_turno(redis, pausa_do_turno) -> None:
    """Pausa pelo mouse → cartão → o turno pausa (sem desistir em 90 s) → Permitir → a ferramenta
    roda de novo e segue: manda ``retomar`` à ponte e observa."""
    cartoes = CartoesComTurno()
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    canal = CanalPc(redis)
    with AppFalso(canal, usuario_id, sessao_id, lambda c: _ok(_observacao())) as app:
        pc = await _pc(provedor, usuario_id, bot)
        pc.contexto = _contexto(usuario_id, bot)
        await canal.marcar_pausado(usuario_id, bot)  # a ponte viu o mouse (rota /pausar)
        with pytest.raises(TurnoPausado) as pausa:
            await pc.observar()
        aprovacao_id = UUID(pausa.value.valor["aprovacao_id"])
        assert cartoes.vinculados and cartoes.vinculados[0][0] == aprovacao_id
        assert cartoes.abertos[0][1]["tipo"] == "pc_retomar"
        assert await canal.quem_tem_a_vez(usuario_id) is None  # vez solta: o usuário decide

        cartoes.situacao[aprovacao_id] = "permitida"  # o usuário clicou em Permitir
        retomada = await _pc(provedor, usuario_id, bot)  # a retomada roda a ferramenta de novo
        retomada.contexto = _contexto(usuario_id, bot)
        observacao = await retomada.observar()
        assert observacao.janelas[0].programa == "notepad.exe"
        assert app.operacoes()[-2:] == ["retomar", "observar"]
        assert not await canal.esta_pausado(usuario_id, bot)


async def test_cartao_decidido_logo_nao_pausa_o_turno(redis, pausa_do_turno) -> None:
    cartoes = CartoesComTurno()
    cartoes.decidir_ao_abrir = "permitida"
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    canal = CanalPc(redis)
    with AppFalso(canal, usuario_id, sessao_id, lambda c: _ok(_observacao())) as app:
        pc = await _pc(provedor, usuario_id, bot)
        pc.contexto = _contexto(usuario_id, bot)
        await canal.marcar_pausado(usuario_id, bot)
        await pc.observar()
        assert not cartoes.vinculados and app.operacoes() == ["retomar", "observar"]


async def test_cartao_vencido_com_turno_pausado_vale_recusa(redis, pausa_do_turno) -> None:
    cartoes = CartoesComTurno()
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    canal = CanalPc(redis)
    with AppFalso(canal, usuario_id, sessao_id, lambda c: _ok(_observacao())):
        pc = await _pc(provedor, usuario_id, bot)
        pc.contexto = _contexto(usuario_id, bot)
        await canal.marcar_pausado(usuario_id, bot)
        with pytest.raises(TurnoPausado) as pausa:
            await pc.observar()
        cartoes.situacao[UUID(pausa.value.valor["aprovacao_id"])] = "expirada"
        retomada = await _pc(provedor, usuario_id, bot)
        retomada.contexto = _contexto(usuario_id, bot)
        with pytest.raises(ErroFerramenta, match="preferiu ficar com o computador"):
            await retomada.observar()
        assert len(cartoes.abertos) == 1  # não abre outro cartão em laço


async def test_pausa_no_meio_da_acao_nao_pausa_o_turno(redis, pausa_do_turno) -> None:
    """A ação pode ter ficado pela metade: a retomada repetiria a chamada inteira. O bot recebe o
    aviso e a próxima chamada (observar) é que pausa."""
    cartoes = CartoesComTurno()
    cartoes.sempre.add("notepad.exe")
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    canal = CanalPc(redis)

    def responder(comando):
        if comando["operacao"] == "agir":
            return _erro("pausado")
        return _ok(_observacao())

    with AppFalso(canal, usuario_id, sessao_id, responder):
        pc = await _pc(provedor, usuario_id, bot)
        pc.contexto = _contexto(usuario_id, bot)
        with pytest.raises(ErroFerramenta) as erro:
            await pc.agir(_resolvida(tipo="digitar", texto="Produto"))
        assert str(erro.value) == PAUSOU_NO_MEIO and not cartoes.vinculados
        proxima = await _pc(provedor, usuario_id, bot)
        proxima.contexto = _contexto(usuario_id, bot)
        with pytest.raises(TurnoPausado):
            await proxima.observar()


async def test_programa_novo_no_meio_do_lote_nao_pausa_o_turno(redis, pausa_do_turno) -> None:
    cartoes = CartoesComTurno()
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    canal = CanalPc(redis)
    await canal.permitir_uma_vez(usuario_id, bot, "notepad.exe")
    respostas = iter(
        [_ok(), _erro("programa_nao_permitido", programa="EXCEL.EXE", titulo="Pasta1 - Excel")]
    )
    with AppFalso(canal, usuario_id, sessao_id, lambda c: next(respostas)):
        pc = await _pc(provedor, usuario_id, bot)
        pc.contexto = _contexto(usuario_id, bot)
        await pc.agir(_resolvida(tipo="tecla", tecla="Tab"))
        with pytest.raises(ErroFerramenta, match="Chame de novo a mesma ação"):
            await pc.agir(_resolvida(tipo="digitar", texto="Café"))
        assert not cartoes.vinculados
        assert cartoes.abertos[0][1]["condicao"]["programa"] == "excel.exe"


# ---------- abrir programa pelo nome ----------


async def test_abrir_programa_passa_pelo_cartao_e_pela_ponte(redis) -> None:
    cartoes = CartoesFalsos()
    cartoes.decidir_ao_abrir = "permitida"
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    canal = CanalPc(redis)
    vistos: list = []

    def responder(comando):
        if comando["operacao"] != "abrir_programa":
            return _ok(_observacao())
        vistos.append(comando["dados"])
        if "excel.exe" not in comando["dados"]["programas_permitidos"]:
            return _erro("programa_nao_permitido", programa="excel.exe", titulo="Excel")
        return _ok({"janela": "77", "programa": "excel.exe", "na_frente": True})

    with AppFalso(canal, usuario_id, sessao_id, responder):
        pc = await _pc(provedor, usuario_id, bot)
        resultado = await pc.abrir_programa("Excel")
        assert resultado["na_frente"] is True and pc.feitas == 1
        assert [v["programa"] for v in vistos] == ["Excel", "Excel"]
        assert cartoes.abertos[0][1]["condicao"]["programa"] == "excel.exe"


async def test_abrir_programa_fora_da_lista_ou_nao_instalado(redis) -> None:
    cartoes = CartoesFalsos()
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    canal = CanalPc(redis)
    respostas = iter([_erro("nao_abrivel", mensagem="cmd"), _erro("nao_instalado", titulo="Excel")])
    with AppFalso(canal, usuario_id, sessao_id, lambda c: next(respostas)):
        pc = await _pc(provedor, usuario_id, bot)
        with pytest.raises(ErroFerramenta) as erro:
            await pc.abrir_programa("cmd")
        assert str(erro.value) == NAO_ABRIVEL
        with pytest.raises(ErroFerramenta, match="Excel não está instalado"):
            await pc.abrir_programa("Excel")


# ---------- teclado de edição sem o juiz (teclado_local.py) ----------

from app.computador.teclado_local import (  # noqa: E402
    EDITORES_LOCAIS,
    dispensa_juiz,
    marcar,
    programas_do_teclado_local,
)


def test_teclado_de_edicao_dispensa_o_juiz_so_no_pc_e_so_teclado() -> None:
    tabela = {"tipo": "digitar", "texto": "Produto\tQtd\tPreço\nCafé\t2\t10,50\n"}
    assert dispensa_juiz("computador_agir", {"alvo": "pc_usuario", "acoes": [tabela]})
    assert dispensa_juiz(
        "computador_agir",
        {"alvo": "pc_usuario", "acoes": [{"tipo": "tecla", "tecla": "Escape"}, tabela]},
    )
    for acoes in (
        [{"tipo": "clicar", "x": 10, "y": 10}],  # clique pode apertar "Enviar"
        [{"tipo": "tecla", "tecla": "ctrl+Return"}],  # envia e-mail em vários programas
        [{"tipo": "tecla", "tecla": "alt+F4"}],
        [{"tipo": "digitar", "texto": "S3nh@Forte!9"}],
        [],
    ):
        assert not dispensa_juiz("computador_agir", {"alvo": "pc_usuario", "acoes": acoes})
    assert not dispensa_juiz("computador_agir", {"alvo": "virtual", "acoes": [tabela]})
    assert not dispensa_juiz("navegador_acao", {"alvo": "pc_usuario", "acoes": [tabela]})


async def test_juiz_dispensado_restringe_a_ponte_aos_editores_locais(redis) -> None:
    cartoes = CartoesFalsos()
    cartoes.sempre |= {"excel.exe", "chrome.exe"}
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    canal = CanalPc(redis)
    vistos: list = []

    def responder(comando):
        vistos.append(comando["dados"].get("programas_permitidos"))
        return _ok()

    with AppFalso(canal, usuario_id, sessao_id, responder):
        marcar(True)
        pc = await _pc(provedor, usuario_id, bot)
        pc.so_programas = programas_do_teclado_local()
        await pc.agir(_resolvida(tipo="tecla", tecla="Tab"))
        marcar(False)
        assert programas_do_teclado_local() is None
    assert vistos == [["excel.exe"]] and "chrome.exe" not in EDITORES_LOCAIS


# ---------- árvore compacta (servico.texto_da_arvore) ----------


def test_arvore_em_linhas_celulas_primeiro_e_so_o_que_mudou() -> None:
    from app.computador.servico import texto_da_arvore

    faixa = [{"ref": f"e{i}", "papel": "botão", "nome": f"Botão {i}"} for i in range(1, 120)]
    celula = {"ref": "e200", "papel": "item de tabela", "nome": "A1", "valor": "Produto"}
    foco = {"ref": "e201", "papel": "item de tabela", "nome": "A2", "estados": ["foco"]}
    texto = texto_da_arvore([*faixa, celula, foco])
    assert texto.index('e200 item de tabela "A1" = "Produto"') < texto.index("Botão 1")
    assert 'e201 item de tabela "A2" [foco]' in texto
    depois = texto_da_arvore([*faixa, celula, foco], [*faixa, foco])
    assert "Botão 7" not in depois and "+119 elementos iguais" in depois
    assert '"A1" = "Produto"' in depois
