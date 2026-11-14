"""Farol-2, item 1: o bot vê a tela (``app/computador/visao.py``).

O formato da imagem, a escala das coordenadas, "só a última captura" e o aviso de modelo sem
visão, com um agente real do LangChain e um modelo que grava o que recebe. O computador de
verdade (contêiner) está em ``tests/integracao/test_computador_visao.py``.
"""

from __future__ import annotations

import base64
import io
from typing import Any
from uuid import uuid4

import fakeredis.aioredis
import pytest
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from pydantic import Field

from app.computador.interface import (
    AcaoComputador,
    AcaoResolvida,
    Alvo,
    ArquivoArea,
    Janela,
    Observacao,
    Tela,
    parece_senha,
)
from app.computador.pc_usuario import ProvedorPcUsuario
from app.computador.servico import ServicoComputador
from app.computador.visao import (
    COM_VISAO,
    LARGURA_MAXIMA_VISAO,
    MAX_BYTES_PNG,
    SEM_VISAO,
    MiddlewareVisaoTela,
    preparar_imagem,
    texto_da_captura,
)
from app.ferramentas.base import ContextoFerramenta


def _png(tamanho: tuple[int, int], cor: tuple[int, int, int] = (20, 40, 90)) -> bytes:
    from PIL import Image

    saida = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(saida, format="PNG")
    return saida.getvalue()


def _png_ruidoso(tamanho: tuple[int, int]) -> bytes:
    import os

    from PIL import Image

    saida = io.BytesIO()
    Image.frombytes("RGB", tamanho, os.urandom(tamanho[0] * tamanho[1] * 3)).save(
        saida, format="PNG"
    )
    return saida.getvalue()


# ---------- formato e escala ----------


def test_tela_pequena_vai_em_escala_1_para_1() -> None:
    imagem = preparar_imagem(_png((1280, 800)))
    assert (imagem.largura, imagem.altura) == (1280, 800)
    assert imagem.tipo == "image/png" and imagem.fator == 1.0
    texto = texto_da_captura(imagem, 3)
    assert "@c3" in texto and "escala 1:1" in texto and "1280x800" in texto


def test_tela_grande_e_reduzida_e_o_texto_explica_a_conta() -> None:
    imagem = preparar_imagem(_png((2560, 1440)))
    assert imagem.largura == LARGURA_MAXIMA_VISAO and imagem.altura == 720
    assert (imagem.largura_real, imagem.altura_real) == (2560, 1440)
    assert imagem.fator == 2.0
    texto = texto_da_captura(imagem, 7, Alvo.PC_USUARIO)
    assert "2560x1440" in texto and "1280x720" in texto
    assert "multiplique por 2,00" in texto and "computador do usuário" in texto


def test_imagem_pesada_cai_para_jpeg_e_o_bloco_tem_o_formato_do_openai() -> None:
    imagem = preparar_imagem(_png_ruidoso((1280, 800)))
    assert imagem.tipo == "image/jpeg" and len(imagem.dados) < MAX_BYTES_PNG * 2
    bloco = imagem.bloco()
    assert bloco["type"] == "image_url"
    url = bloco["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == imagem.dados


# ---------- o agente real recebe a imagem ----------


class _Gravador(BaseChatModel):
    """Responde com o roteiro e guarda as mensagens de cada chamada."""

    roteiro: list[AIMessage]
    vistos: list[list[Any]] = Field(default_factory=list)
    model: str = "gravador"

    def bind_tools(self, tools: Any, **_kw: Any) -> Any:
        return self

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **_kw: Any):
        self.vistos.append(list(messages))
        indice = min(len(self.vistos) - 1, len(self.roteiro) - 1)
        return ChatResult(generations=[ChatGeneration(message=self.roteiro[indice])])

    @property
    def _llm_type(self) -> str:
        return "gravador"


def _chamada(nome: str, args: dict[str, Any], id_: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": nome, "args": args, "id": id_}])


class _Computador:
    alvo = Alvo.VIRTUAL

    def __init__(self, tamanho: tuple[int, int]) -> None:
        self.tamanho = tamanho
        self.cor = 10

    async def observar(self) -> Observacao:
        return Observacao(
            tela=Tela(_png(self.tamanho, (self.cor, 40, 90)), *self.tamanho),
            janelas=[Janela("0x1", "Chromium", 0, 0, *self.tamanho, ativa=True)],
        )

    async def agir(self, acao: AcaoResolvida) -> None:
        self.cor += 30

    async def listar_arquivos(self, pasta: str) -> list[ArquivoArea]:
        return []

    async def ler_arquivo(self, caminho: str, limite: int) -> bytes:
        return b""

    async def escrever_arquivo(self, caminho: str, dados: bytes) -> None:
        return None


class _Provedor:
    def __init__(self, tamanho: tuple[int, int]) -> None:
        self.computador = _Computador(tamanho)

    async def obter(self, usuario_id: Any, agente_id: Any) -> _Computador:
        return self.computador

    async def desligar(self, agente_id: Any) -> bool:
        return True


def _servico(tamanho: tuple[int, int] = (1280, 800)) -> ServicoComputador:
    async def publicar(_evento: Any, _usuario: Any) -> None:
        return None

    return ServicoComputador(
        provedores={Alvo.VIRTUAL: _Provedor(tamanho), Alvo.PC_USUARIO: ProvedorPcUsuario()},
        redis=fakeredis.aioredis.FakeRedis(),
        publicar=publicar,
    )


def _ferramentas(servico: ServicoComputador, ctx: ContextoFerramenta) -> list[StructuredTool]:
    async def computador_observar() -> str:
        return await servico.observar(ctx)

    async def computador_agir(x: int, y: int) -> str:
        return await servico.agir(ctx, [AcaoComputador(tipo="clicar", x=x, y=y)])

    return [
        StructuredTool.from_function(
            coroutine=computador_observar, name="computador_observar", description="Olha a tela."
        ),
        StructuredTool.from_function(
            coroutine=computador_agir, name="computador_agir", description="Clica."
        ),
    ]


def _imagens(mensagens: list[Any]) -> list[dict[str, Any]]:
    achadas = []
    for m in mensagens:
        if isinstance(m.content, list):
            achadas += [b for b in m.content if b.get("type") == "image_url"]
    return achadas


async def _rodar(modelo: _Gravador, servico: ServicoComputador, *, ve: bool) -> ContextoFerramenta:
    ctx = ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4())
    agente = create_agent(
        model=modelo,
        tools=_ferramentas(servico, ctx),
        system_prompt="Você é um bot.",
        middleware=[
            MiddlewareVisaoTela(ctx.agente_id, servico=lambda: servico, tem_visao=lambda _m: ve)
        ],
    )
    await agente.ainvoke({"messages": [HumanMessage("abra o site")]})
    return ctx


async def test_modelo_com_visao_recebe_so_a_ultima_captura(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.computador.servico.ESPERA_DEPOIS_DE_AGIR_S", 0)
    modelo = _Gravador(
        roteiro=[
            _chamada("computador_observar", {}, "a"),
            _chamada("computador_agir", {"x": 10, "y": 10}, "b"),
            _chamada("computador_agir", {"x": 20, "y": 20}, "c"),
            AIMessage(content="pronto"),
        ]
    )
    await _rodar(modelo, _servico((2560, 1440)), ve=True)
    # chamada 1: nada visto ainda; 2, 3 e 4: exatamente UMA imagem, a da leitura mais nova
    assert [len(_imagens(v)) for v in modelo.vistos] == [0, 1, 1, 1]
    ultima = modelo.vistos[-1][-1]
    assert isinstance(ultima, HumanMessage)
    texto = ultima.content[0]["text"]
    assert "leitura @c3" in texto and "multiplique por 2,00" in texto
    assert ultima.content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    # o aviso vai no prompt de sistema; a imagem nunca vai para o histórico do agente
    assert COM_VISAO in modelo.vistos[-1][0].content
    assert not any(
        isinstance(m, ToolMessage) and isinstance(m.content, list) for m in modelo.vistos[-1]
    )


async def test_modelo_sem_visao_fica_so_no_texto_e_o_prompt_avisa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.computador.servico.ESPERA_DEPOIS_DE_AGIR_S", 0)
    modelo = _Gravador(
        roteiro=[_chamada("computador_observar", {}, "a"), AIMessage(content="pronto")]
    )
    await _rodar(modelo, _servico(), ve=False)
    assert all(_imagens(v) == [] for v in modelo.vistos)
    sistema = modelo.vistos[-1][0].content
    assert SEM_VISAO in sistema and "não enxerga imagens" in sistema
    assert COM_VISAO not in sistema


async def test_captura_de_outra_leitura_ou_de_outro_turno_nao_vai() -> None:
    servico = _servico()
    ctx = ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4())
    await servico.observar(ctx)  # leitura @c1 (a que o serviço guarda)
    middleware = MiddlewareVisaoTela(
        ctx.agente_id, servico=lambda: servico, tem_visao=lambda _m: True
    )

    def tool(geracao: int) -> ToolMessage:
        return ToolMessage(
            content=f"Computador virtual (1280x800 px), leitura @c{geracao}.",
            name="computador_observar",
            tool_call_id="x",
        )

    assert await middleware._mensagem_da_tela([HumanMessage("oi"), tool(1)]) is not None
    # o texto cita @c5, o worker guarda @c1: melhor sem imagem do que com uma imagem errada
    assert await middleware._mensagem_da_tela([HumanMessage("oi"), tool(5)]) is None
    # nova mensagem do usuário depois da ferramenta: tela de outro turno não volta
    assert await middleware._mensagem_da_tela([tool(1), HumanMessage("e agora?")]) is None
    # sem nenhuma ferramenta de tela
    assert await middleware._mensagem_da_tela([HumanMessage("oi")]) is None


async def test_troca_de_modelo_no_meio_do_turno_vale_a_cada_chamada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quem decide é o modelo da chamada: o predicado recebe ``request.model``."""
    monkeypatch.setattr("app.computador.servico.ESPERA_DEPOIS_DE_AGIR_S", 0)
    modelo = _Gravador(
        roteiro=[_chamada("computador_observar", {}, "a"), AIMessage(content="pronto")]
    )
    servico = _servico()
    ctx = ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4())
    vistos: list[Any] = []

    def enxerga(m: Any) -> bool:
        vistos.append(m)
        return False

    agente = create_agent(
        model=modelo,
        tools=_ferramentas(servico, ctx),
        middleware=[MiddlewareVisaoTela(ctx.agente_id, servico=lambda: servico, tem_visao=enxerga)],
    )
    await agente.ainvoke({"messages": [HumanMessage("oi")]})
    assert vistos and all(m is modelo for m in vistos)


# ---------- regra de senha refinada ----------


@pytest.mark.parametrize(
    "texto",
    ["Pedido#123A", "NF-2024-001", "PED-1234", "OS_5521B", "Protocolo/2024.77", "Pedido#123A"],
)
def test_codigos_de_negocio_nao_sao_senha(texto: str) -> None:
    assert not parece_senha(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "Cafe@2024",
        "Xk9#mPq2rT",
        "Ab1!Ab1!",
        "Senha#abcd9",  # forma de código, mas quase sem dígito: é uma senha com enfeite
        "Pedido#123A!",  # símbolo fora dos separadores de código
        "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
    ],
)
def test_ainda_recusa_o_que_parece_senha(texto: str) -> None:
    assert parece_senha(texto)


# ---------- ligação na montagem do agente ----------


async def test_montagem_liga_a_visao_so_para_quem_tem_computador(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.agentes.middleware import montar_middleware
    from app.agentes.montagem import ContextoAgente
    from app.computador.visao import com_visao_do_computador

    async def com_visao(_usuario_id: Any) -> frozenset[str]:
        return frozenset({"openai/gpt-4o"})

    monkeypatch.setattr("app.llm.falso.modelo_falso_ativo", lambda: False)
    monkeypatch.setattr("app.computador.visao.nomes_de_modelos_com_visao", com_visao)

    def contexto(extras: list[str]) -> ContextoAgente:
        return ContextoAgente(
            usuario_id=uuid4(),
            agente_id=uuid4(),
            conversa_id=uuid4(),
            papel="individual",
            ferramentas_extras=extras,
        )

    sem = await com_visao_do_computador(contexto(["buscar_web"]))
    assert sem.modelo_enxerga is None  # sem computador: nada muda

    com = await com_visao_do_computador(contexto(["computador_observar", "computador_agir"]))
    assert com.modelo_enxerga is not None
    assert com.modelo_enxerga(SimpleNamespace(model="openai/gpt-4o")) is True
    assert com.modelo_enxerga(SimpleNamespace(model="groq/llama")) is False

    modelo = SimpleNamespace(model="openai/gpt-4o")
    assert any(isinstance(m, MiddlewareVisaoTela) for m in montar_middleware(com, [modelo]))
    assert not any(isinstance(m, MiddlewareVisaoTela) for m in montar_middleware(sem, [modelo]))
