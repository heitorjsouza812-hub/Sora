"""C3 (Vela-3): controle do PC do usuário pelo app de desktop, sem app de verdade.

O app de desktop é simulado por uma tarefa que busca comandos no canal (como o long-poll) e
responde. As rotas e o canal com Postgres, Redis e a API reais estão em
``tests/integracao/test_computador_pc.py``; a ponte Rust tem os próprios testes
(``cargo test`` em ``app/src-tauri``).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest

from app.computador.interface import AcaoComputador, AcaoResolvida, Alvo, Janela
from app.computador.pc_usuario import (
    ABRIR,
    ARQUIVOS,
    DESLIGADO_PARA_O_BOT,
    PARADO,
    PAUSADO_ESPERANDO,
    RECUSA,
    RECUSOU_RETOMAR,
    RETOMADO,
    SENHA,
    ComputadorPcUsuario,
    ProvedorPcUsuario,
    normalizar_programa,
    observacao_do_app,
)
from app.computador.pc_usuario_canal import AgentePc, CanalPc
from app.computador.pc_usuario_cartoes import FERRAMENTA_PROGRAMA
from app.computador.servico import ServicoComputador
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta


def _png(tamanho: tuple[int, int] = (64, 40), cor: tuple[int, int, int] = (5, 6, 8)) -> bytes:
    from PIL import Image

    saida = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(saida, format="PNG")
    return saida.getvalue()


def _observacao(cor: tuple[int, int, int] = (5, 6, 8)) -> dict[str, Any]:
    return {
        "png": base64.b64encode(_png(cor=cor)).decode(),
        "largura": 64,
        "altura": 40,
        "janelas": [
            {
                "id": "1001",
                "titulo": "Sem título - Bloco de Notas",
                "x": 0,
                "y": 0,
                "largura": 64,
                "altura": 40,
                "ativa": True,
                "programa": "C:\\Windows\\Notepad.exe",
            },
            {"id": "1002", "titulo": "Cofre — Bitwarden", "programa": "Bitwarden.exe"},
        ],
        "arvore": [
            {
                "ref": "e1",
                "papel": "campo de texto",
                "nome": "Texto",
                "valor": "olá",
                "centro": [10, 10],
            },
            {
                "ref": "e2",
                "papel": "campo de texto",
                "nome": "Senha",
                "valor": "segredo123!",
                "centro": [20, 20],
                "estados": ["senha", "foco", "inventado"],
            },
        ],
    }


class CartoesFalsos:
    """Aprovações em memória; o teste decide pelo usuário."""

    def __init__(self) -> None:
        self.abertos: list[tuple[UUID, dict[str, Any], str]] = []
        self.situacao: dict[UUID, str] = {}
        self.sempre: set[str] = set()
        self.decidir_ao_abrir: str | None = None
        self.aberto = asyncio.Event()

    async def agente(self, usuario_id: UUID, agente_id: UUID) -> AgentePc | None:
        return AgentePc(id=agente_id, nome="Atlas", cor="#56A8FF")

    async def abrir(self, usuario_id, agente_id, acao, motivo) -> UUID:
        aprovacao_id = uuid4()
        self.abertos.append((aprovacao_id, acao, motivo))
        self.aberto.set()
        self.situacao[aprovacao_id] = self.decidir_ao_abrir or "pendente"
        if self.decidir_ao_abrir == "sempre":
            self.situacao[aprovacao_id] = "permitida"
            self.sempre.add(acao["condicao"]["programa"])
        return aprovacao_id

    async def status(self, usuario_id, aprovacao_id) -> str | None:
        return self.situacao.get(aprovacao_id)

    async def programas_sempre(self, usuario_id, agente_id) -> set[str]:
        return set(self.sempre)


Responder = Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]


class AppFalso:
    """O app de desktop: busca comandos pelo canal (long-poll) e responde, como a ponte Rust."""

    def __init__(self, canal: CanalPc, usuario_id: UUID, sessao_id: str, responder: Responder):
        self.canal, self.usuario_id, self.sessao_id = canal, usuario_id, sessao_id
        self.responder = responder
        self.recebidos: list[dict[str, Any]] = []
        self._tarefa: asyncio.Task | None = None

    async def _rodar(self) -> None:
        while True:
            comando = await self.canal.proximo_comando(self.usuario_id, self.sessao_id, 0.2)
            if comando is None:
                continue
            self.recebidos.append(comando)
            resposta = self.responder(comando)
            if asyncio.iscoroutine(resposta):
                resposta = await resposta
            await self.canal.responder(self.usuario_id, self.sessao_id, comando["id"], resposta)

    def __enter__(self) -> AppFalso:
        self._tarefa = asyncio.create_task(self._rodar())
        return self

    def __exit__(self, *_: object) -> None:
        assert self._tarefa is not None
        self._tarefa.cancel()

    def operacoes(self) -> list[str]:
        return [c["operacao"] for c in self.recebidos]


def _ok(resultado: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": True, "resultado": resultado or {}}


def _erro(codigo: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "erro": {"codigo": codigo, **extra}}


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def cartoes() -> CartoesFalsos:
    return CartoesFalsos()


async def _conectar(redis, cartoes, *autorizados: UUID) -> tuple[UUID, str, ProvedorPcUsuario]:
    usuario_id = uuid4()
    sessao_id = await CanalPc(redis).registrar_sessao(usuario_id, list(autorizados), "PC da Ana")
    provedor = ProvedorPcUsuario(redis=redis, cartoes=cartoes, espera_cartao_s=0.5)
    return usuario_id, sessao_id, provedor


async def _pc(
    provedor: ProvedorPcUsuario, usuario_id: UUID, agente_id: UUID
) -> ComputadorPcUsuario:
    computador = await provedor.obter(usuario_id, agente_id)
    computador.intervalo_cartao_s = 0.02
    return computador


def _resolvida(**campos: Any) -> AcaoResolvida:
    acao = AcaoComputador(**campos)
    ponto = (acao.x, acao.y) if acao.x is not None and acao.y is not None else None
    return AcaoResolvida(acao=acao, ponto=ponto, tecla=acao.tecla)


# ---------- sessão e canal ----------


async def test_sem_app_conectado_recusa(redis, cartoes) -> None:
    provedor = ProvedorPcUsuario(redis=redis, cartoes=cartoes)
    with pytest.raises(ErroFerramenta, match=RECUSA[:30]):
        await provedor.obter(uuid4(), uuid4())


async def test_redis_fora_do_ar_vira_recusa(cartoes) -> None:
    class RedisQuebrado:
        async def get(self, *_: object) -> None:
            from redis.exceptions import ConnectionError

            raise ConnectionError("fora")

    with pytest.raises(ErroFerramenta, match=RECUSA[:30]):
        await ProvedorPcUsuario(redis=RedisQuebrado(), cartoes=cartoes).obter(uuid4(), uuid4())


async def test_bot_desligado_no_app_e_recusado(redis, cartoes) -> None:
    ligado, desligado = uuid4(), uuid4()
    usuario_id, _, provedor = await _conectar(redis, cartoes, ligado)
    with pytest.raises(ErroFerramenta, match="não ligou o controle"):
        await provedor.obter(usuario_id, desligado)
    assert DESLIGADO_PARA_O_BOT.startswith("O usuário não ligou")
    computador = await provedor.obter(usuario_id, ligado)
    assert computador.alvo is Alvo.PC_USUARIO and computador.agente.nome == "Atlas"


async def test_sessao_nova_substitui_a_anterior_e_atualiza_autorizados(redis) -> None:
    canal, usuario_id, bot = CanalPc(redis), uuid4(), uuid4()
    primeira = await canal.registrar_sessao(usuario_id, [bot], "PC 1")
    assert await canal.tocar(usuario_id, primeira)
    segunda = await canal.registrar_sessao(usuario_id, [], "PC 2")
    assert not await canal.tocar(usuario_id, primeira)  # só um PC por conta
    assert not await canal.atualizar_autorizados(usuario_id, primeira, [bot])
    assert await canal.atualizar_autorizados(usuario_id, segunda, [bot, bot])
    assert (await canal.sessao(usuario_id))["autorizados"] == [str(bot)]
    assert await canal.encerrar_sessao(usuario_id, segunda)
    assert await canal.sessao(usuario_id) is None


async def test_comando_tem_prazo_e_uso_unico(redis) -> None:
    canal, usuario_id = CanalPc(redis), uuid4()
    sessao_id = await canal.registrar_sessao(usuario_id, [], "PC")
    agente = AgentePc(uuid4(), "Atlas", "#56A8FF")

    # vencido: o app nunca recebe
    await canal.enviar(usuario_id, sessao_id, agente, "observar", {}, 0.05, esperar=False)
    await asyncio.sleep(0.1)
    assert await canal.proximo_comando(usuario_id, sessao_id, 0) is None

    async def worker() -> dict[str, Any] | None:
        return await canal.enviar(usuario_id, sessao_id, agente, "observar", {}, 5)

    tarefa = asyncio.create_task(worker())
    comando = await canal.proximo_comando(usuario_id, sessao_id, 2)
    assert comando is not None and comando["operacao"] == "observar"
    assert comando["agente"] == {"id": str(agente.id), "nome": "Atlas", "cor": "#56A8FF"}
    # outra conta não responde nem recebe
    assert await canal.responder(uuid4(), sessao_id, comando["id"], _ok()) == "nao_encontrado"
    assert await canal.proximo_comando(uuid4(), sessao_id, 0) is None
    assert await canal.responder(usuario_id, sessao_id, comando["id"], _ok({"a": 1})) == "ok"
    assert await canal.responder(usuario_id, sessao_id, comando["id"], _ok()) == "usado"
    assert await tarefa == _ok({"a": 1})
    assert await canal.responder(usuario_id, sessao_id, "x" * 80, _ok()) == "nao_encontrado"


async def test_app_que_nao_responde_estoura_o_prazo(redis) -> None:
    canal, usuario_id = CanalPc(redis), uuid4()
    sessao_id = await canal.registrar_sessao(usuario_id, [], "PC")
    agente = AgentePc(uuid4(), "Atlas", "#56A8FF")
    with pytest.raises(ErroFerramenta, match="não respondeu a tempo"):
        await canal.enviar(usuario_id, sessao_id, agente, "observar", {}, 0.2)
    comando = await canal.proximo_comando(usuario_id, sessao_id, 0)
    assert comando is None  # venceu: ninguém executa depois


async def test_um_bot_por_vez(redis) -> None:
    canal, usuario_id = CanalPc(redis), uuid4()
    atlas, luna = AgentePc(uuid4(), "Atlas", "#56A8FF"), AgentePc(uuid4(), "Luna", "#AC80FF")
    await canal.pegar_vez(usuario_id, atlas)
    await canal.pegar_vez(usuario_id, atlas)  # o mesmo bot renova
    with pytest.raises(ErroFerramenta, match="O PC está em uso por Atlas"):
        await canal.pegar_vez(usuario_id, luna)
    assert not await canal.soltar_vez(usuario_id, luna.id)  # só quem tem a vez solta
    assert await canal.soltar_vez(usuario_id, atlas.id)
    await canal.pegar_vez(usuario_id, luna)


# ---------- observar ----------


def test_observacao_do_app_e_limpa() -> None:
    observacao = observacao_do_app(_observacao())
    assert observacao.tela.largura == 64 and observacao.tela.png.startswith(b"\x89PNG")
    notas, cofre = observacao.janelas
    assert notas.programa == "notepad.exe" and notas.ativa and notas.id_nativo == "1001"
    assert cofre.titulo == "(programa bloqueado para bots)"  # nem o título aparece
    texto, senha = observacao.arvore or []
    assert texto["valor"] == "olá" and texto["centro"] == [10, 10]
    assert "valor" not in senha and senha["estados"] == ["senha", "foco"]
    for ruim in ({"png": "não é base64"}, {"png": base64.b64encode(b"GIF89a").decode()}):
        with pytest.raises(ErroFerramenta, match="captura inválida"):
            observacao_do_app(ruim)
    assert normalizar_programa("C:\\Program Files\\App\\App.EXE") == "app.exe"


async def test_observar_pega_a_vez_e_devolve_a_tela(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    with AppFalso(CanalPc(redis), usuario_id, sessao_id, lambda _c: _ok(_observacao())) as app:
        observacao = await computador.observar()
    assert app.operacoes() == ["observar"]
    assert observacao.janelas[0].titulo.startswith("Sem título")
    assert (await CanalPc(redis).quem_tem_a_vez(usuario_id))["nome"] == "Atlas"


# ---------- agir: programa, senha, abrir, arquivos ----------


async def test_primeira_acao_no_programa_pede_cartao_e_uma_vez_libera(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)

    def responder(comando: dict[str, Any]) -> dict[str, Any]:
        if "notepad.exe" in comando["dados"]["programas_permitidos"]:
            return _ok()
        return _erro("programa_nao_permitido", programa="Notepad.exe", titulo="Sem título")

    async def decidir() -> None:
        await cartoes.aberto.wait()
        cartoes.situacao[cartoes.abertos[0][0]] = "permitida"  # Permitir uma vez

    with AppFalso(CanalPc(redis), usuario_id, sessao_id, responder) as app:
        decisao = asyncio.create_task(decidir())
        await computador.agir(_resolvida(tipo="digitar", texto="Lista de compras"))
        await decisao
        # segunda ação no mesmo programa: sem cartão novo
        await computador.agir(_resolvida(tipo="tecla", tecla="Return"))
    _aprovacao_id, acao, _motivo = cartoes.abertos[0]
    assert len(cartoes.abertos) == 1
    assert acao["tipo"] == "pc_programa" and acao["ferramenta"] == FERRAMENTA_PROGRAMA
    assert acao["condicao"] == {"programa": "notepad.exe"}
    assert "Atlas quer usar notepad.exe" in acao["resumo"]
    agir = [c for c in app.recebidos if c["operacao"] == "agir"]
    assert len(agir) == 3
    assert agir[0]["dados"]["acao"] == {"tipo": "digitar", "texto": "Lista de compras"}
    assert agir[2]["dados"]["acao"] == {"tipo": "tecla", "tecla": "Return"}


async def test_sempre_permitir_e_recusar(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)

    def responder(comando: dict[str, Any]) -> dict[str, Any]:
        permitidos = comando["dados"]["programas_permitidos"]
        alvo = "excel.exe" if comando["dados"]["acao"]["tipo"] == "clicar" else "notepad.exe"
        return _ok() if alvo in permitidos else _erro("programa_nao_permitido", programa=alvo)

    with AppFalso(CanalPc(redis), usuario_id, sessao_id, responder):
        cartoes.decidir_ao_abrir = "sempre"
        await computador.agir(_resolvida(tipo="tecla", tecla="Return"))
        assert cartoes.sempre == {"notepad.exe"}
        cartoes.decidir_ao_abrir = "negada"
        with pytest.raises(ErroFerramenta, match=r"não deixou usar excel.exe"):
            await computador.agir(_resolvida(tipo="clicar", x=5, y=5))
        # recusado continua recusado sem abrir outro cartão
        with pytest.raises(ErroFerramenta, match=r"não deixou usar excel.exe"):
            await computador.agir(_resolvida(tipo="clicar", x=5, y=5))
    assert len(cartoes.abertos) == 2


async def test_cartao_sem_resposta_nao_prende_o_bot(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    with AppFalso(
        CanalPc(redis),
        usuario_id,
        sessao_id,
        lambda _c: _erro("programa_nao_permitido", programa="mspaint.exe"),
    ):
        with pytest.raises(ErroFerramenta, match="ainda não respondeu"):
            await computador.agir(_resolvida(tipo="clicar", x=1, y=1))
        with pytest.raises(ErroFerramenta, match="ainda não respondeu"):
            await computador.agir(_resolvida(tipo="clicar", x=1, y=1))
    assert len(cartoes.abertos) == 1  # o mesmo cartão, sem duplicar


async def test_programa_bloqueado_nunca_vira_cartao(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    respostas = iter(
        [
            _erro("programa_nao_permitido", programa="C:\\x\\KeePass.exe"),
            _erro("programa_bloqueado", programa="consent.exe"),
            _erro("senha"),
        ]
    )
    with AppFalso(CanalPc(redis), usuario_id, sessao_id, lambda _c: next(respostas)):
        for _ in range(2):
            with pytest.raises(ErroFerramenta, match="bloqueado para bots"):
                await computador.agir(_resolvida(tipo="clicar", x=1, y=1))
        with pytest.raises(ErroFerramenta, match="campo é de senha"):
            await computador.agir(_resolvida(tipo="digitar", texto="oi"))
    assert cartoes.abertos == []


async def test_senha_abrir_e_arquivos_nem_saem_do_servidor(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    with AppFalso(CanalPc(redis), usuario_id, sessao_id, lambda _c: _ok()) as app:
        with pytest.raises(ErroFerramenta, match=SENHA[:20]):
            await computador.agir(_resolvida(tipo="digitar", texto="Tr0ub4dor&3x"))
        with pytest.raises(ErroFerramenta, match=ABRIR[:20]):
            await computador.agir(_resolvida(tipo="abrir", programa="terminal"))
        for chamada in (
            computador.listar_arquivos(""),
            computador.ler_arquivo("a.txt", 10),
            computador.escrever_arquivo("a.txt", b"x"),
        ):
            with pytest.raises(ErroFerramenta, match=ARQUIVOS[:20]):
                await chamada
    assert app.recebidos == []


async def test_vez_de_outro_bot(redis, cartoes) -> None:
    atlas, luna = uuid4(), uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, atlas, luna)
    pc_atlas = await _pc(provedor, usuario_id, atlas)
    pc_luna = await _pc(provedor, usuario_id, luna)
    with AppFalso(CanalPc(redis), usuario_id, sessao_id, lambda _c: _ok(_observacao())) as app:
        await pc_atlas.observar()
        with pytest.raises(ErroFerramenta, match="em uso por Atlas"):
            await pc_luna.observar()
    assert app.operacoes() == ["observar"]


# ---------- pausa e Parar ----------


async def test_mexer_no_mouse_pausa_e_cartao_retoma(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    estado = {"pausado": False}

    def responder(comando: dict[str, Any]) -> dict[str, Any]:
        if comando["operacao"] == "retomar":
            estado["pausado"] = False
            return _ok()
        if comando["operacao"] == "agir" and not estado.get("ja_pausou"):
            estado["pausado"] = estado["ja_pausou"] = True  # o usuário mexeu no mouse
        if estado["pausado"]:
            return _erro("pausado")
        return _ok(_observacao()) if comando["operacao"] == "observar" else _ok()

    async def decidir() -> None:
        await cartoes.aberto.wait()
        cartoes.situacao[cartoes.abertos[0][0]] = "permitida"

    cartoes.sempre.add("notepad.exe")
    with AppFalso(CanalPc(redis), usuario_id, sessao_id, responder) as app:
        decisao = asyncio.create_task(decidir())
        with pytest.raises(ErroFerramenta, match=RETOMADO[:30]):
            await computador.agir(_resolvida(tipo="digitar", texto="oi"))
        await decisao
        await computador.agir(_resolvida(tipo="digitar", texto="oi"))
    acao = cartoes.abertos[0][1]
    assert acao["tipo"] == "pc_retomar" and "ferramenta" not in acao  # sem "sempre" aqui
    assert "Atlas pausou" in acao["resumo"]
    assert app.operacoes() == ["agir", "retomar", "agir"]
    assert not await CanalPc(redis).esta_pausado(usuario_id, bot)


async def test_pausa_sem_resposta_e_recusa(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    with AppFalso(CanalPc(redis), usuario_id, sessao_id, lambda _c: _erro("pausado")) as app:
        with pytest.raises(ErroFerramenta, match=PAUSADO_ESPERANDO[:30]):
            await computador.observar()
        # pausado: a próxima chamada nem chega ao app antes do cartão
        with pytest.raises(ErroFerramenta, match=PAUSADO_ESPERANDO[:30]):
            await computador.observar()
        assert app.operacoes() == ["observar"]
        cartoes.situacao[cartoes.abertos[0][0]] = "negada"
        with pytest.raises(ErroFerramenta, match=RECUSOU_RETOMAR[:30]):
            await computador.observar()
        await asyncio.sleep(0.3)
    assert app.operacoes() == ["observar", "encerrar"]
    canal = CanalPc(redis)
    assert await canal.esta_parado(usuario_id, bot)
    assert await canal.quem_tem_a_vez(usuario_id) is None


async def test_parar_tira_a_vez_e_bloqueia(redis, cartoes) -> None:
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    canal = CanalPc(redis)
    await canal.permitir_uma_vez(usuario_id, bot, "notepad.exe")
    with AppFalso(canal, usuario_id, sessao_id, lambda _c: _erro("parado")) as app:
        with pytest.raises(ErroFerramenta, match=PARADO[:30]):
            await computador.observar()
        with pytest.raises(ErroFerramenta, match=PARADO[:30]):
            await computador.observar()
    assert app.operacoes() == ["observar"]
    assert await canal.quem_tem_a_vez(usuario_id) is None
    assert await canal.programas_uma_vez(usuario_id, bot) == set()


# ---------- pelo serviço (as ferramentas computador_*) ----------


async def test_servico_com_o_pc_nunca_guarda_o_texto_digitado(redis, cartoes, monkeypatch) -> None:
    monkeypatch.setattr("app.computador.servico.ESPERA_DEPOIS_DE_AGIR_S", 0)
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    cartoes.sempre.add("notepad.exe")
    eventos: list[Any] = []

    async def publicar(evento, _usuario) -> None:
        eventos.append(evento)

    servico = ServicoComputador(
        provedores={Alvo.PC_USUARIO: provedor}, redis=redis, publicar=publicar
    )
    contexto = ContextoFerramenta(usuario_id=usuario_id, agente_id=bot, conversa_id=uuid4())
    digitou: list[bool] = []

    def responder(comando: dict[str, Any]) -> dict[str, Any]:
        # como o Bloco de Notas de verdade: depois de digitar, o título leva a 1ª linha (sem ":")
        if comando["dados"].get("acao", {}).get("tipo") == "digitar":
            digitou.append(True)
        observacao = _observacao()
        if digitou:
            observacao["janelas"][0]["titulo"] = "*Lista de compras - Bloco de notas"
        return _ok(observacao)

    with AppFalso(CanalPc(redis), usuario_id, sessao_id, responder):
        texto = await servico.observar(contexto, Alvo.PC_USUARIO)
        assert "Computador do usuário" in texto and "@c1:j1" in texto
        assert '"ref": "e1"' in texto and "segredo123" not in texto
        texto = await servico.agir(
            contexto,
            [
                AcaoComputador(tipo="clicar", ref="@c1:j1"),
                AcaoComputador(tipo="digitar", texto="Lista de compras"),
            ],
            Alvo.PC_USUARIO,
        )
        assert "2 de 2" in texto
    assert {e.alvo for e in eventos} == {"pc_usuario"}
    assert eventos[-1].acao == "Clicou em @c1:j1; Digitou 16 caracteres"
    rastro = json.dumps([e.model_dump(mode="json") for e in eventos]) + json.dumps(
        {k: await redis.get(k) for k in await redis.keys("computador:estado:*")}
    )
    assert "Lista de compras" not in rastro
    assert eventos[0].janela_ativa == "notepad.exe"
    assert eventos[-1].janela_ativa == "notepad.exe"
    with pytest.raises(ErroFerramenta, match="rotinas sem supervisão"):
        await servico.observar(
            ContextoFerramenta(
                usuario_id=usuario_id, agente_id=bot, conversa_id=uuid4(), sem_supervisao=True
            ),
            Alvo.PC_USUARIO,
        )


async def test_clique_por_ref_de_janela_leva_a_janela(redis, cartoes) -> None:
    resolvida = AcaoResolvida(
        acao=AcaoComputador(tipo="clicar", ref="@c1:j1"),
        janela=Janela("1001", "Bloco", 0, 0, 40, 20, True, "notepad.exe"),
        ponto=(20, 10),
    )
    assert ComputadorPcUsuario.acao_para_app(resolvida) == {
        "tipo": "clicar",
        "x": 20,
        "y": 10,
        "janela": "1001",
    }


# ---------- cartão na lista "Precisa de você" ----------


def test_texto_do_cartao_na_lista_de_atencao() -> None:
    from app.atencao import _texto_acao
    from app.modelos.tabelas import Aprovacao

    cartao = Aprovacao(
        acao={
            "tipo": "pc_programa",
            "ferramenta": FERRAMENTA_PROGRAMA,
            "titulo": "Usar um programa do seu computador",
            "resumo": "Atlas quer usar notepad.exe no seu computador.",
        },
        avaliacao={},
    )
    assert _texto_acao(cartao, "Atlas") == (
        "aprovacao",
        "Usar um programa do seu computador",
        "Atlas quer usar notepad.exe no seu computador.",
    )


def test_passo_do_painel_trabalho_nao_guarda_o_texto_digitado() -> None:
    """Vela-6: o passo (``workers/portas.py``) guarda os parâmetros da ferramenta; em
    ``computador_agir`` o texto digitado vira só a contagem de caracteres."""
    from app.ferramentas.rotulos import parametros_sem_segredos

    argumentos = {
        "alvo": "pc_usuario",
        "acoes": [
            {"tipo": "clicar", "ref": "@c1:j1"},
            {"tipo": "digitar", "texto": "Lista de compras"},
        ],
    }
    limpos = parametros_sem_segredos(argumentos, "computador_agir")
    assert "Lista de compras" not in json.dumps(limpos)
    assert limpos["acoes"][1] == {"tipo": "digitar", "texto": "[16 caracteres]"}
    assert limpos["acoes"][0] == {"tipo": "clicar", "ref": "@c1:j1"}
    assert argumentos["acoes"][1]["texto"] == "Lista de compras"  # o original não muda
    # outras ferramentas seguem como antes
    assert parametros_sem_segredos({"consulta": "café"}, "buscar_web") == {"consulta": "café"}
