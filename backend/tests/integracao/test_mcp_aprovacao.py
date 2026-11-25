# ruff: noqa: F811
"""Aprovação das ferramentas MCP (tarefa 0.3, ``docs/SORA_PLANO_CORRECOES_NO_LUGAR.md`` §3.3).

O furo: numa conversa **supervisionada** com mais de 20 ferramentas MCP, a de escrita
(``delete_everything``) rodava pelo ``conectores_executar_ferramenta`` sem o cartão "Precisa de
você": o catálogo montado em ``servidores.py`` não tinha gancho de revisão e o
``MiddlewareRevisor`` isenta a meta-ferramenta de execução.

Aqui tudo é de verdade (API em uvicorn, worker ARQ, Postgres e Redis do Docker, montagem do
agente, catálogo, revisor e juiz), menos duas peças:

- o servidor MCP: ``MultiServerMCPClient`` falso com N ferramentas, a última é
  ``delete_everything``, que anota cada execução em ``efeitos`` (o efeito contável);
- o modelo: ``_Adversario`` tenta **todos** os caminhos que o turno oferece até
  ``delete_everything`` (a ferramenta direta, o executor do catálogo pelo id e o executor de
  dentro de um catálogo aninhado). Ele registra as ferramentas que o agente ofereceu a cada
  chamada, para o teste saber por qual caminho passou.

Casos:

- 25 ferramentas, papéis ``pesquisador`` (etapa da cadeia da Sora) e ``individual`` (bot 1:1):
  abre o cartão (linha pendente em ``aprovacoes`` + evento ``aprovacao.pedida``) e o efeito
  fica em zero. **Falha no código antigo.**
- Regressão: 5 ferramentas nos dois papéis (caminho direto, revisado pelo ``MiddlewareRevisor``)
  e rotina sem supervisão (a ferramenta de escrita nem é oferecida), com 5 e 25.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from langchain_core.tools import StructuredTool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modelos.enumeracoes import StatusAprovacao, TipoAgente
from app.modelos.tabelas import Agente, Aprovacao, Usuario
from tests.integracao.test_fase_b_pronto import (  # noqa: F401
    ambiente_fase_b,
    ambiente_fase_b_arq,
    entrar,
    ler_sse,
    servicos_fase_b,
)

pytestmark = pytest.mark.integracao

SERVIDOR = "inventario"
ALVO = f"mcp__{SERVIDOR}__delete_everything"
ARGUMENTOS = {"alvo": "tudo"}
EXECUTOR = "conectores_executar_ferramenta"
LIMITE_S = 90.0


# ---------------------------------------------------------------- servidor MCP falso


def _instalar_mcp(monkeypatch: pytest.MonkeyPatch, quantidade: int) -> list[dict[str, Any]]:
    """Servidor MCP com ``quantidade`` ferramentas: ``get_item_*`` (leitura) e, por último,
    ``delete_everything``. Devolve a lista em que cada execução de ``delete_everything`` entra."""
    efeitos: list[dict[str, Any]] = []

    async def consultar(item: str = "") -> str:
        return f"Item {item or 'qualquer'}: 3 unidades."

    async def delete_everything(alvo: str) -> str:
        efeitos.append({"alvo": alvo})
        return "Inventário apagado."

    class ClienteMCP:
        def __init__(self, conexoes: dict[str, Any]) -> None:
            assert list(conexoes) == [SERVIDOR]

        async def get_tools(self, *, server_name: str) -> list[StructuredTool]:
            assert server_name == SERVIDOR
            leitura = [
                StructuredTool.from_function(
                    coroutine=consultar,
                    name=f"get_item_{i}",
                    description="Consulta um item do inventário.",
                )
                for i in range(quantidade - 1)
            ]
            escrita = StructuredTool.from_function(
                coroutine=delete_everything,
                name="delete_everything",
                description="Apaga todo o inventário.",
            )
            return [*leitura, escrita]

    monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", ClienteMCP)
    return efeitos


# ---------------------------------------------------------------- modelo roteirizado


def _nome_da_ferramenta(ferramenta: Any) -> str | None:
    if isinstance(ferramenta, dict):
        return ferramenta.get("name") or (ferramenta.get("function") or {}).get("name")
    return getattr(ferramenta, "name", None)


def _tentativas(oferecidas: list[str]) -> list[tuple[str, dict[str, Any]]]:
    """Todos os caminhos até ``delete_everything`` que o turno oferece, na ordem."""
    tentativas: list[tuple[str, dict[str, Any]]] = []
    if ALVO in oferecidas:  # ferramenta direta (até 20, papel não enxuto)
        tentativas.append((ALVO, dict(ARGUMENTOS)))
    if EXECUTOR in oferecidas:
        # catálogo: o executor pelo id da ferramenta de verdade
        tentativas.append((EXECUTOR, {"id": ALVO, "argumentos": dict(ARGUMENTOS)}))
        # catálogo dentro de catálogo (o de ``servidores.py`` como item do catálogo do turno):
        # o executor de dentro, chamado pelo de fora
        tentativas.append(
            (EXECUTOR, {"id": EXECUTOR, "argumentos": {"id": ALVO, "argumentos": ARGUMENTOS}})
        )
    return tentativas


def _proximo_passo(oferecidas: list[str], mensagens: list[Any]) -> Any:
    from langchain_core.messages import AIMessage

    feitas = {
        json.dumps([chamada["name"], chamada["args"]], sort_keys=True)
        for mensagem in mensagens
        if isinstance(mensagem, AIMessage)
        for chamada in mensagem.tool_calls
    }
    for nome, argumentos in _tentativas(oferecidas):
        if json.dumps([nome, argumentos], sort_keys=True) not in feitas:
            return AIMessage(
                content="",
                tool_calls=[{"name": nome, "args": argumentos, "id": f"call_{uuid4().hex[:12]}"}],
            )
    return AIMessage(content="Pronto.")


def _adversario(papel: str, ofertas: list[list[str]]) -> Any:
    from langchain_core.outputs import ChatGeneration, ChatResult

    from app.llm.falso import _com_uso, classe_modelo_falso

    class Adversario(classe_modelo_falso()):
        """Modelo falso (com o ``_stream`` que preserva chamadas) que tenta apagar o inventário."""

        ofertas: Any = None

        def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
            self.ofertas.append(sorted(filter(None, map(_nome_da_ferramenta, tools))))
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            oferecidas = self.ofertas[-1] if self.ofertas else []
            resposta = _com_uso(_proximo_passo(oferecidas, messages), messages)
            return ChatResult(generations=[ChatGeneration(message=resposta)])

    return Adversario(
        papel=papel, model_name=f"roteiro/{papel}", messages=iter(()), ofertas=ofertas
    )


def _roteirizar(
    monkeypatch: pytest.MonkeyPatch, modulo: ModuleType, papeis: set[str]
) -> list[list[str]]:
    """Troca o modelo falso desses papéis pelo adversário. Devolve as ofertas registradas."""
    ofertas: list[list[str]] = []
    original = modulo.criar_modelo_falso

    def criar(papel: str) -> Any:
        return _adversario(papel, ofertas) if papel in papeis else original(papel)

    monkeypatch.setattr(modulo, "criar_modelo_falso", criar)
    return ofertas


# ---------------------------------------------------------------- apoio


async def _esperar(condicao: Callable[[], Awaitable[Any]], limite_s: float = LIMITE_S) -> Any:
    async def laco() -> Any:
        while not (valor := await condicao()):  # noqa: ASYNC110
            await asyncio.sleep(0.2)
        return valor

    return await asyncio.wait_for(laco(), limite_s)


async def _entrar(cliente: httpx.AsyncClient, fabrica: async_sessionmaker, email: str) -> dict:
    """``entrar`` sem o limite de cadastros: os containers valem para o módulo inteiro e o
    ``ambiente_fase_b_arq`` não esvazia o Redis entre os testes."""
    from redis.asyncio import Redis

    from app.core.config import obter_configuracao

    redis = Redis.from_url(obter_configuracao().redis_url)
    try:
        chaves = [chave async for chave in redis.scan_iter(match="limite:*")]
        if chaves:
            await redis.delete(*chaves)
    finally:
        await redis.aclose()
    return await entrar(cliente, fabrica, email)


async def _usuario(fabrica: async_sessionmaker, email: str) -> UUID:
    async with fabrica() as sessao:
        usuario_id = await sessao.scalar(select(Usuario.id).where(Usuario.email == email))
    assert usuario_id is not None
    return usuario_id


async def _cartoes(fabrica: async_sessionmaker, usuario_id: UUID) -> list[Aprovacao]:
    async with fabrica() as sessao:
        return list(
            await sessao.scalars(select(Aprovacao).where(Aprovacao.usuario_id == usuario_id))
        )


async def _conectar(cliente: httpx.AsyncClient, auth: dict) -> None:
    resposta = await cliente.post(
        "/v1/conectores",
        headers=auth,
        json={"nome": "Inventario", "url": "http://127.0.0.1:8080/mcp"},
    )
    assert resposta.status_code == 201, resposta.text


# ---------------------------------------------------------------- o furo (§3.3)


@pytest.mark.parametrize("quantidade", [25, 5])
@pytest.mark.parametrize("papel", ["pesquisador", "individual"])
async def test_conversa_supervisionada_nao_apaga_sem_cartao(
    ambiente_fase_b_arq: tuple[str, async_sessionmaker],
    monkeypatch: pytest.MonkeyPatch,
    papel: str,
    quantidade: int,
) -> None:
    """Escrita MCP numa conversa supervisionada: cartão aberto, ``delete_everything`` não roda.

    ``pesquisador``: etapa da cadeia que a Sora monta para "crie uma campanha…".
    ``individual``: bot 1:1 (``responder_direto``; ``[aprovacao]`` faz o worker rodar o agente de
    verdade com o modelo falso em vez da resposta curta pronta)."""
    import app.orquestrador.modelos as orquestrador_modelos

    url, fabrica = ambiente_fase_b_arq
    efeitos = _instalar_mcp(monkeypatch, quantidade)
    papeis = {"pesquisador"} if papel == "pesquisador" else {"individual", "agente_individual"}
    ofertas = _roteirizar(monkeypatch, orquestrador_modelos, papeis)
    email = f"mcp-{papel}-{quantidade}@exemplo.com"
    async with httpx.AsyncClient(base_url=url, timeout=60) as cliente:
        auth = await _entrar(cliente, fabrica, email)
        usuario_id = await _usuario(fabrica, email)
        await _conectar(cliente, auth)
        if papel == "individual":
            async with fabrica() as sessao:
                bot = Agente(
                    usuario_id=usuario_id,
                    tipo=TipoAgente.INDIVIDUAL,
                    nome="Bia",
                    papel="Cuida do inventário",
                )
                sessao.add(bot)
                await sessao.commit()
            corpo = {
                "agente_id": str(bot.id),
                "texto": "Limpe o inventário inteiro [aprovacao]",
                "anexos": [],
            }
        else:
            corpo = {"texto": "crie uma campanha para minha cafeteria", "anexos": []}
        resposta = await cliente.post("/v1/conversas", headers=auth, json=corpo)
        assert resposta.status_code == 201, resposta.text
        conversa_id = resposta.json()["id"]

        async def desfecho() -> bool:
            return bool(efeitos) or bool(await _cartoes(fabrica, usuario_id))

        await _esperar(desfecho)
        await asyncio.sleep(1)  # com o turno pausado no cartão, nada mais pode rodar

        assert efeitos == [], (
            f"{ALVO} executou sem cartão 'Precisa de você' "
            f"(papel={papel}, {quantidade} ferramentas MCP): {efeitos}"
        )
        cartoes = await _cartoes(fabrica, usuario_id)
        assert len(cartoes) == 1, [c.acao for c in cartoes]
        (cartao,) = cartoes
        assert cartao.status == StatusAprovacao.PENDENTE
        # revisado com o nome da ferramenta de verdade, não com o da meta-ferramenta
        assert cartao.acao["ferramenta"] == ALVO, cartao.acao
        eventos = await ler_sse(
            cliente,
            conversa_id,
            auth,
            ate=lambda nome, dados: (
                nome == "aprovacao.pedida" and dados.get("aprovacao_id") == str(cartao.id)
            ),
            limite_s=30,
        )
        assert eventos[-1][0] == "aprovacao.pedida"

        # o caminho que este caso exercita
        vistas = {nome for oferta in ofertas for nome in oferta}
        assert vistas, "o agente não chamou o modelo roteirizado"
        if quantidade <= 20:
            assert ALVO in vistas, sorted(vistas)  # direto, pelo MiddlewareRevisor
        else:
            assert ALVO not in vistas and EXECUTOR in vistas, sorted(vistas)  # catálogo
        assert efeitos == []


@pytest.mark.parametrize("quantidade", [25, 5])
async def test_rotina_sem_supervisao_nem_oferece_a_escrita_mcp(
    ambiente_fase_b_arq: tuple[str, async_sessionmaker],
    monkeypatch: pytest.MonkeyPatch,
    quantidade: int,
) -> None:
    """Rotina (``sem_supervisao=True``): ``delete_everything`` não é oferecida nem roda, e a rotina
    não abre cartão. Regressão: passa antes e depois da correção."""
    import workers.rotinas as worker_rotinas
    from app.conectores.carregar import ferramentas_dos_conectores

    url, fabrica = ambiente_fase_b_arq
    efeitos = _instalar_mcp(monkeypatch, quantidade)
    ofertas = _roteirizar(monkeypatch, worker_rotinas, {"rotina"})
    email = f"mcp-rotina-{quantidade}@exemplo.com"
    async with httpx.AsyncClient(base_url=url, timeout=60) as cliente:
        auth = await _entrar(cliente, fabrica, email)
        usuario_id = await _usuario(fabrica, email)
        await _conectar(cliente, auth)
        # o conector carrega neste ambiente: a rotina não passa só por ficar sem ferramentas
        assert await ferramentas_dos_conectores(usuario_id)
        sem = await ferramentas_dos_conectores(usuario_id, sem_supervisao=True)
        assert ALVO not in {f.name for f in sem}

        criada = await cliente.post(
            "/v1/rotinas",
            headers=auth,
            json={"titulo": "Limpeza", "pedido": "Limpe o inventário.", "daqui_segundos": 1},
        )
        assert criada.status_code == 201, criada.text
        rotina_id = criada.json()["id"]

        async def terminou() -> list[dict]:
            resposta = await cliente.get(f"/v1/rotinas/{rotina_id}/execucoes", headers=auth)
            assert resposta.status_code == 200, resposta.text
            return [e for e in resposta.json() if e["concluida_em"]]

        await _esperar(terminou)
        vistas = {nome for oferta in ofertas for nome in oferta}
        assert vistas, "a rotina não chamou o modelo roteirizado"
        assert ALVO not in vistas, sorted(vistas)
        assert efeitos == [], efeitos
        assert await _cartoes(fabrica, usuario_id) == []


# ---------------------------------------------------------------- teste de conexão


@pytest.mark.parametrize("quantidade", [5, 25])
async def test_conexao_mcp_lista_os_nomes_reais(
    ambiente_fase_b, monkeypatch: pytest.MonkeyPatch, quantidade: int
) -> None:
    class ClienteMCP:
        def __init__(self, conexoes):
            assert list(conexoes) == ["inventario"]

        async def get_tools(self, *, server_name):
            assert server_name == "inventario"

            async def consultar() -> str:
                pytest.fail("O teste de conexão nunca executa ferramentas")

            return [
                StructuredTool.from_function(
                    coroutine=consultar, name=f"get_item_{i}", description="Consulta um item"
                )
                for i in range(quantidade)
            ]

    monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", ClienteMCP)
    cliente, fabrica, _ = ambiente_fase_b
    auth = await entrar(cliente, fabrica, f"mcp-catalogo-{quantidade}@exemplo.com")
    resposta = await cliente.post(
        "/v1/conectores",
        headers=auth,
        json={"nome": "Inventario", "url": "http://127.0.0.1:8080/mcp"},
    )
    assert resposta.status_code == 201, resposta.text
    conector_id = resposta.json()["id"]

    teste = await cliente.post(f"/v1/conectores/{conector_id}/testar", headers=auth)
    assert teste.status_code == 200, teste.text
    assert teste.json() == {
        "ok": True,
        "erro": None,
        "ferramentas": [f"mcp__inventario__get_item_{i}" for i in range(quantidade)],
    }
    lista = await cliente.get("/v1/conectores", headers=auth)
    assert lista.status_code == 200, lista.text
    (conector,) = lista.json()
    assert conector["estado"] == "ok" and conector["n_ferramentas"] == quantidade
