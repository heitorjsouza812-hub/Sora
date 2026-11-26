# ruff: noqa: F811
"""Aprovação das ferramentas MCP (tarefa 0.3, ``docs/SORA_PLANO_CORRECOES_NO_LUGAR.md`` §3.3).

O furo: numa conversa **supervisionada** com mais de 20 ferramentas MCP, a de escrita
(``delete_everything``) rodava pelo ``conectores_executar_ferramenta`` sem o cartão "Precisa de
você": o catálogo montado em ``servidores.py`` não tinha gancho de revisão e o
``MiddlewareRevisor`` isenta a meta-ferramenta de execução.

Aqui tudo é de verdade (API em uvicorn, worker ARQ, Postgres e Redis do Docker, montagem do
agente, catálogo, revisor e juiz), menos duas peças:

- o servidor MCP: ``MultiServerMCPClient`` falso com N ferramentas, ``get_item_*`` (leitura, cada
  execução entra em ``leituras``) e, por último, ``delete_everything`` (cada execução entra em
  ``efeitos``, o efeito contável);
- o modelo: um roteiro fixo por caso (uma chamada de ferramenta por passo, depois o texto
  ``FIM``). Ele anota as ferramentas oferecidas, as chamadas que fez e as respostas
  (``ToolMessage``) que recebeu, para o teste saber o que de fato rodou.

Casos (cada um num turno próprio: o primeiro cartão pausa o turno, então um roteiro só não
mostraria as tentativas seguintes):

- supervisionado, papéis ``pesquisador`` (etapa da cadeia da Sora) e ``individual`` (bot 1:1):
  (a) 5 ferramentas, chamada direta → cartão; (b) 25, executor do catálogo pelo id → cartão;
  (c) 25, executor aninhado dentro do executor → recusado, sem cartão nem efeito; (d) 25, carregar
  o esquema e chamar pelo nome, que o turno não oferece → cartão (o ``MiddlewareRevisor`` revisa
  pelo nome antes de qualquer execução);
- supervisionado com o grupo ``navegador`` no catálogo (bot 1:1 com o navegador ligado): sem
  navegador no pedido, a escrita MCP vai direto ao modelo; citando o navegador (``superficie``),
  vai pelo catálogo. Nos dois, cartão com o nome real e efeito zero;
- rotina sem supervisão, 5 e 25: a leitura MCP roda, a rotina termina ``enviada`` e a escrita não
  é oferecida (com 25, nem está no catálogo).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from langchain_core.tools import StructuredTool
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ferramentas.permissoes import FERRAMENTAS_NAVEGADOR
from app.modelos.enumeracoes import (
    AutorMensagem,
    StatusAprovacao,
    StatusCadeia,
    StatusEtapa,
    TipoAgente,
)
from app.modelos.tabelas import Agente, Aprovacao, Cadeia, Etapa, Mensagem, Usuario
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
LEITURA = f"mcp__{SERVIDOR}__get_item_0"
ARGUMENTOS = {"alvo": "tudo"}
EXECUTOR = "conectores_executar_ferramenta"
CARREGAR = "conectores_carregar_ferramenta"
BUSCAR = "conectores_buscar_ferramentas"
FIM = "Fim do roteiro."
LIMITE_S = 90.0


# ---------------------------------------------------------------- servidor MCP falso


@dataclass
class MCPFalso:
    efeitos: list[dict[str, Any]] = field(default_factory=list)
    """Cada execução de ``delete_everything``."""
    leituras: list[str] = field(default_factory=list)
    """Cada execução de ``get_item_*`` (``nome:item``)."""


def _instalar_mcp(monkeypatch: pytest.MonkeyPatch, quantidade: int) -> MCPFalso:
    """Servidor MCP com ``quantidade`` ferramentas: ``get_item_*`` (leitura) e, por último,
    ``delete_everything``."""
    mcp = MCPFalso()

    def leitura(i: int) -> StructuredTool:
        async def consultar(item: str = "") -> str:
            mcp.leituras.append(f"get_item_{i}:{item}")
            return f"Item {item or 'qualquer'}: 3 unidades."

        return StructuredTool.from_function(
            coroutine=consultar, name=f"get_item_{i}", description="Consulta um item do inventário."
        )

    async def delete_everything(alvo: str) -> str:
        mcp.efeitos.append({"alvo": alvo})
        return "Inventário apagado."

    class ClienteMCP:
        def __init__(self, conexoes: dict[str, Any]) -> None:
            assert list(conexoes) == [SERVIDOR]

        async def get_tools(self, *, server_name: str) -> list[StructuredTool]:
            assert server_name == SERVIDOR
            escrita = StructuredTool.from_function(
                coroutine=delete_everything,
                name="delete_everything",
                description="Apaga todo o inventário.",
            )
            return [*(leitura(i) for i in range(quantidade - 1)), escrita]

    monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", ClienteMCP)
    return mcp


# ---------------------------------------------------------------- modelo roteirizado

Passo = tuple[str, dict[str, Any]]


@dataclass
class Registro:
    """O que o modelo roteirizado viu e fez."""

    ofertas: list[list[str]] = field(default_factory=list)
    descricoes: dict[str, str] = field(default_factory=dict)
    chamadas: list[Passo] = field(default_factory=list)
    respostas: list[tuple[str, str]] = field(default_factory=list)
    """``(ferramenta, conteúdo)`` de cada ``ToolMessage`` que voltou ao modelo."""
    terminou: bool = False

    @property
    def vistas(self) -> set[str]:
        return {nome for oferta in self.ofertas for nome in oferta}


def _nome_e_descricao(ferramenta: Any) -> tuple[str | None, str]:
    if isinstance(ferramenta, dict):
        funcao = ferramenta.get("function") or {}
        return (
            ferramenta.get("name") or funcao.get("name"),
            ferramenta.get("description") or funcao.get("description") or "",
        )
    return getattr(ferramenta, "name", None), getattr(ferramenta, "description", "") or ""


def _roteirizado(papel: str, roteiro: list[Passo], registro: Registro) -> Any:
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from app.llm.falso import _com_uso, classe_modelo_falso

    class Roteirizado(classe_modelo_falso()):
        """Modelo falso (com o ``_stream`` que preserva chamadas) que segue o roteiro do caso."""

        roteiro: Any = None
        registro: Any = None

        def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
            nomes = []
            for ferramenta in tools:
                nome, descricao = _nome_e_descricao(ferramenta)
                if nome:
                    nomes.append(nome)
                    self.registro.descricoes[nome] = descricao
            self.registro.ofertas.append(sorted(nomes))
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            feitas = [
                chamada
                for mensagem in messages
                if isinstance(mensagem, AIMessage)
                for chamada in mensagem.tool_calls
            ]
            nomes = {chamada["id"]: chamada["name"] for chamada in feitas}
            self.registro.respostas = [
                (nomes.get(m.tool_call_id, m.name or "?"), str(m.content))
                for m in messages
                if isinstance(m, ToolMessage)
            ]
            self.registro.chamadas = [(c["name"], c["args"]) for c in feitas]
            if len(feitas) < len(self.roteiro):
                nome, argumentos = self.roteiro[len(feitas)]
                self.registro.chamadas.append((nome, argumentos))
                resposta = AIMessage(
                    content="",
                    tool_calls=[
                        {"name": nome, "args": argumentos, "id": f"call_{uuid4().hex[:12]}"}
                    ],
                )
            else:
                self.registro.terminou = True
                resposta = AIMessage(content=FIM)
            return ChatResult(generations=[ChatGeneration(message=_com_uso(resposta, messages))])

    return Roteirizado(
        papel=papel,
        model_name=f"roteiro/{papel}",
        messages=iter(()),
        roteiro=roteiro,
        registro=registro,
    )


def _roteirizar(
    monkeypatch: pytest.MonkeyPatch, modulo: ModuleType, papeis: set[str], roteiro: list[Passo]
) -> Registro:
    """Troca o modelo falso desses papéis pelo roteirizado. Devolve o registro dele."""
    registro = Registro()
    original = modulo.criar_modelo_falso

    def criar(papel: str) -> Any:
        return _roteirizado(papel, roteiro, registro) if papel in papeis else original(papel)

    monkeypatch.setattr(modulo, "criar_modelo_falso", criar)
    return registro


# ---------------------------------------------------------------- apoio


async def _esperar(
    condicao: Callable[[], Awaitable[Any]], motivo: str, limite_s: float = LIMITE_S
) -> Any:
    async def laco() -> Any:
        while not (valor := await condicao()):  # noqa: ASYNC110
            await asyncio.sleep(0.2)
        return valor

    try:
        return await asyncio.wait_for(laco(), limite_s)
    except TimeoutError:
        pytest.fail(f"{motivo} em {limite_s:.0f} s")


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


def _email(prefixo: str) -> str:
    """Único a cada execução: o banco vale para o módulo inteiro (e para o ``--count``)."""
    return f"{prefixo.replace('_', '-')}-{uuid4().hex[:8]}@exemplo.com"


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


async def _pausas_gravadas(fabrica: async_sessionmaker, thread: str) -> int:
    """Interrupções gravadas no checkpoint do LangGraph (``thread`` aceita ``%``)."""
    async with fabrica() as sessao:
        return int(
            await sessao.scalar(
                text(
                    "select count(*) from checkpoint_writes "
                    "where channel = '__interrupt__' and thread_id like :thread"
                ).bindparams(thread=thread)
            )
            or 0
        )


async def _etapa_do_pesquisador(fabrica: async_sessionmaker, conversa_id: str) -> Etapa | None:
    async with fabrica() as sessao:
        return await sessao.scalar(
            select(Etapa)
            .join(Cadeia, Cadeia.id == Etapa.cadeia_id)
            .where(Cadeia.conversa_id == UUID(conversa_id), Etapa.especialista == "pesquisador")
        )


async def _iniciar_turno(
    cliente: httpx.AsyncClient,
    fabrica: async_sessionmaker,
    auth: dict,
    usuario_id: UUID,
    papel: str,
    ferramentas_do_bot: list[str] | None = None,
    pedido: str = "Limpe o inventário inteiro",
) -> str:
    """Abre a conversa do caso e devolve o id dela."""
    if papel == "individual":
        async with fabrica() as sessao:
            bot = Agente(
                usuario_id=usuario_id,
                tipo=TipoAgente.INDIVIDUAL,
                nome="Bia",
                papel="Cuida do inventário",
                ferramentas=list(ferramentas_do_bot or []),
            )
            sessao.add(bot)
            await sessao.commit()
        # ``[aprovacao]`` faz o worker rodar o agente de verdade com o modelo falso, em vez da
        # resposta curta pronta. Sem navegador nem PC no pedido, o turno não liga a
        # ``superficie`` (que deixaria direto só essas ferramentas).
        corpo = {
            "agente_id": str(bot.id),
            "texto": f"{pedido} [aprovacao]",
            "anexos": [],
        }
    else:
        corpo = {"texto": "crie uma campanha para minha cafeteria", "anexos": []}
    resposta = await cliente.post("/v1/conversas", headers=auth, json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


async def _esperar_pausa(
    fabrica: async_sessionmaker, papel: str, conversa_id: str, cartao: Aprovacao
) -> None:
    """O cartão aparece antes do checkpoint da pausa: espera a pausa gravada (e, na cadeia, a
    etapa em ``aguardando_aprovacao``) para afirmar que o turno parou ali."""
    if papel == "pesquisador":
        assert cartao.etapa_id is not None
        thread = f"etapa:{cartao.etapa_id}"

        async def etapa_pausada() -> bool:
            etapa = await _etapa_do_pesquisador(fabrica, conversa_id)
            return etapa is not None and etapa.status == StatusEtapa.AGUARDANDO_APROVACAO

        await _esperar(etapa_pausada, "a etapa do pesquisador não ficou aguardando aprovação")
    else:
        thread = f"conversa:{conversa_id}%"

    async def pausa() -> bool:
        return await _pausas_gravadas(fabrica, thread) > 0

    await _esperar(pausa, f"a pausa não foi gravada no checkpoint ({thread})")


async def _esperar_fim_sem_pausa(
    fabrica: async_sessionmaker, papel: str, conversa_id: str, registro: Registro
) -> None:
    """Turno que não pausa: o roteiro chegou ao fim e o worker fechou o turno."""

    async def fim_do_roteiro() -> bool:
        return registro.terminou

    try:
        await asyncio.wait_for(_esperar(fim_do_roteiro, "fim do roteiro"), LIMITE_S + 1)
    except BaseException:
        etapa = await _etapa_do_pesquisador(fabrica, conversa_id)
        pytest.fail(
            "o modelo roteirizado não chegou ao fim do roteiro: "
            f"chamadas={registro.chamadas} respostas={registro.respostas} "
            f"etapa={etapa and (etapa.status, etapa.erro)}"
        )
    if papel == "pesquisador":

        async def etapa_fechada() -> Etapa | None:
            etapa = await _etapa_do_pesquisador(fabrica, conversa_id)
            pendentes = {StatusEtapa.PENDENTE, StatusEtapa.EXECUTANDO}
            return etapa if etapa is not None and etapa.status not in pendentes else None

        etapa = await _esperar(etapa_fechada, "a etapa do pesquisador não terminou")
        assert etapa.status != StatusEtapa.AGUARDANDO_APROVACAO, etapa.status

        async def cadeia_parada() -> bool:
            async with fabrica() as sessao:
                status = await sessao.scalar(
                    select(Cadeia.status).where(Cadeia.conversa_id == UUID(conversa_id))
                )
            return status in {
                StatusCadeia.CONCLUIDA,
                StatusCadeia.FALHOU,
                StatusCadeia.AGUARDANDO_USUARIO,
            }

        await _esperar(cadeia_parada, "a cadeia não parou")
        assert await _pausas_gravadas(fabrica, f"etapa:{etapa.id}") == 0
    else:

        async def resposta_falada() -> bool:
            async with fabrica() as sessao:
                return bool(
                    await sessao.scalar(
                        select(Mensagem.id).where(
                            Mensagem.conversa_id == UUID(conversa_id),
                            Mensagem.autor != AutorMensagem.USUARIO,
                            Mensagem.conteudo == FIM,
                        )
                    )
                )

        await _esperar(resposta_falada, "o worker não fechou o turno do bot")
        assert await _pausas_gravadas(fabrica, f"conversa:{conversa_id}%") == 0


async def _conferir_cartao_do_alvo(
    cliente: httpx.AsyncClient,
    fabrica: async_sessionmaker,
    auth: dict,
    usuario_id: UUID,
    papel: str,
    conversa_id: str,
) -> None:
    """Um cartão pendente, revisado com o nome real da escrita, e o turno pausado nele."""

    async def cartao() -> Aprovacao | None:
        cartoes = await _cartoes(fabrica, usuario_id)
        return cartoes[0] if cartoes else None

    achado = await _esperar(cartao, "o cartão 'Precisa de você' não apareceu")
    await _esperar_pausa(fabrica, papel, conversa_id, achado)
    cartoes = await _cartoes(fabrica, usuario_id)
    assert len(cartoes) == 1, [c.acao for c in cartoes]
    (achado,) = cartoes
    assert achado.status == StatusAprovacao.PENDENTE
    # revisado com o nome da ferramenta de verdade, não com o da meta-ferramenta
    assert achado.acao["ferramenta"] == ALVO, achado.acao
    eventos = await ler_sse(
        cliente,
        conversa_id,
        auth,
        ate=lambda nome, dados: (
            nome == "aprovacao.pedida" and dados.get("aprovacao_id") == str(achado.id)
        ),
        limite_s=30,
    )
    assert eventos[-1][0] == "aprovacao.pedida"


# ---------------------------------------------------------------- o furo (§3.3)

CASOS: dict[str, tuple[int, list[Passo]]] = {
    # (a) até 20 ferramentas vão direto: o ``MiddlewareRevisor`` revisa a escrita
    "a_direta": (5, [(ALVO, ARGUMENTOS)]),
    # (b) acima de 20, o executor do catálogo pelo id: o gancho do catálogo revisa
    "b_executor": (25, [(EXECUTOR, {"id": ALVO, "argumentos": ARGUMENTOS})]),
    # (c) o executor de um catálogo dentro do catálogo (o antigo de ``servidores.py``)
    "c_aninhado": (
        25,
        [(EXECUTOR, {"id": EXECUTOR, "argumentos": {"id": ALVO, "argumentos": ARGUMENTOS}})],
    ),
    # (d) carregar o esquema e chamar pelo nome real, que não foi oferecido
    "d_carregar_e_nome": (25, [(CARREGAR, {"id": ALVO}), (ALVO, ARGUMENTOS)]),
}


@pytest.mark.parametrize("caso", list(CASOS))
@pytest.mark.parametrize("papel", ["pesquisador", "individual"])
async def test_conversa_supervisionada_nao_apaga_sem_cartao(
    ambiente_fase_b_arq: tuple[str, async_sessionmaker],
    monkeypatch: pytest.MonkeyPatch,
    papel: str,
    caso: str,
) -> None:
    """Escrita MCP numa conversa supervisionada nunca roda sem cartão, por nenhum caminho.

    ``pesquisador``: etapa da cadeia que a Sora monta para "crie uma campanha…".
    ``individual``: bot 1:1 (``responder_direto``)."""
    import app.orquestrador.modelos as orquestrador_modelos

    quantidade, roteiro = CASOS[caso]
    url, fabrica = ambiente_fase_b_arq
    mcp = _instalar_mcp(monkeypatch, quantidade)
    papeis = {"pesquisador"} if papel == "pesquisador" else {"individual", "agente_individual"}
    registro = _roteirizar(monkeypatch, orquestrador_modelos, papeis, roteiro)
    email = _email(f"mcp-{papel}-{caso}")
    async with httpx.AsyncClient(base_url=url, timeout=60) as cliente:
        auth = await _entrar(cliente, fabrica, email)
        usuario_id = await _usuario(fabrica, email)
        await _conectar(cliente, auth)
        conversa_id = await _iniciar_turno(cliente, fabrica, auth, usuario_id, papel)

        if caso == "c_aninhado":
            await _esperar_fim_sem_pausa(fabrica, papel, conversa_id, registro)
            assert registro.chamadas == roteiro, registro.chamadas
            assert await _cartoes(fabrica, usuario_id) == []
            # rodou só a chamada do roteiro, e voltou como erro: o catálogo do turno não tem
            # outro executor dentro dele
            ((nome, resposta),) = registro.respostas
            assert nome == EXECUTOR, registro.respostas
            assert resposta.startswith("Erro:") and "desconhecida" in resposta, resposta
        else:
            await _conferir_cartao_do_alvo(cliente, fabrica, auth, usuario_id, papel, conversa_id)
            # o turno parou na última chamada do roteiro: ela não voltou ao modelo
            assert registro.chamadas == roteiro, registro.chamadas
            assert not registro.terminou
            if caso == "d_carregar_e_nome":
                # só o carregar rodou; a escrita chamada pelo nome (que o turno não oferece) foi
                # revisada pelo ``MiddlewareRevisor`` antes de qualquer execução
                ((nome, resposta),) = registro.respostas
                assert nome == CARREGAR, registro.respostas
                carregada = json.loads(resposta)
                assert carregada["id"] == ALVO and carregada["somente_leitura"] is False
            else:
                assert registro.respostas == [], registro.respostas

        # o caminho que este caso exercita
        vistas = registro.vistas
        assert vistas, "o agente não chamou o modelo roteirizado"
        if quantidade <= 20:
            assert ALVO in vistas, sorted(vistas)  # direto, pelo MiddlewareRevisor
        else:
            assert ALVO not in vistas and EXECUTOR in vistas, sorted(vistas)  # catálogo
        assert mcp.efeitos == [], (
            f"{ALVO} executou sem cartão 'Precisa de você' "
            f"(papel={papel}, caso={caso}): {mcp.efeitos}"
        )
        assert mcp.leituras == []


PEDIDOS_COM_NAVEGADOR: dict[str, tuple[str, list[Passo]]] = {
    # pedido sem navegador nem PC: as 5 do MCP vão direto, ao lado do catálogo do navegador
    "mcp_direto": ("Limpe o inventário inteiro", [(ALVO, ARGUMENTOS)]),
    # pedido que cita o navegador (``superficie``): as 5 do MCP ficam no catálogo revisado
    "mcp_no_catalogo": (
        "Abra o navegador e limpe o inventário inteiro",
        [(EXECUTOR, {"id": ALVO, "argumentos": ARGUMENTOS})],
    ),
}


@pytest.mark.parametrize("pedido", list(PEDIDOS_COM_NAVEGADOR))
async def test_escrita_mcp_com_o_navegador_no_catalogo(
    ambiente_fase_b_arq: tuple[str, async_sessionmaker],
    monkeypatch: pytest.MonkeyPatch,
    pedido: str,
) -> None:
    """Bot 1:1 com o navegador ligado: o catálogo do turno (``conectores_*``) existe por causa das
    ferramentas extras do navegador (é o trecho de ``catalogo_enxuto`` que o PR #5 alterou).

    Sem navegador no pedido, as 5 do MCP continuam diretas; citando o navegador, vão para o
    catálogo. Nos dois casos a escrita abre o cartão com o nome real e não roda."""
    import app.orquestrador.modelos as orquestrador_modelos

    texto, roteiro = PEDIDOS_COM_NAVEGADOR[pedido]
    url, fabrica = ambiente_fase_b_arq
    mcp = _instalar_mcp(monkeypatch, 5)
    registro = _roteirizar(
        monkeypatch, orquestrador_modelos, {"individual", "agente_individual"}, roteiro
    )
    email = _email(f"mcp-navegador-{pedido}")
    async with httpx.AsyncClient(base_url=url, timeout=60) as cliente:
        auth = await _entrar(cliente, fabrica, email)
        usuario_id = await _usuario(fabrica, email)
        await _conectar(cliente, auth)
        conversa_id = await _iniciar_turno(
            cliente,
            fabrica,
            auth,
            usuario_id,
            "individual",
            list(FERRAMENTAS_NAVEGADOR),
            pedido=texto,
        )
        await _conferir_cartao_do_alvo(
            cliente, fabrica, auth, usuario_id, "individual", conversa_id
        )

        oferta = set(registro.ofertas[-1])
        # o catálogo do turno existe e guarda o grupo navegador
        assert {BUSCAR, CARREGAR, EXECUTOR} <= oferta, sorted(oferta)
        indice = registro.descricoes[BUSCAR]
        assert "navegador:" in indice, indice
        assert "navegador_capturar" not in oferta  # extra do navegador: só pelo catálogo
        if pedido == "mcp_direto":
            # as ferramentas MCP não entram no catálogo: vão direto ao modelo
            assert ALVO in oferta and LEITURA in oferta, sorted(oferta)
            assert f"{SERVIDOR}:" not in indice, indice
        else:
            assert ALVO not in oferta and LEITURA not in oferta, sorted(oferta)
            assert f"{SERVIDOR}:" in indice and "delete_everything" in indice, indice
        # o turno parou na única chamada do roteiro: ela não voltou ao modelo
        assert registro.chamadas == roteiro, registro.chamadas
        assert registro.respostas == [], registro.respostas
        assert not registro.terminou
        assert mcp.efeitos == [], mcp.efeitos
        assert mcp.leituras == []


# ---------------------------------------------------------------- rotina sem supervisão

ROTEIRO_ROTINA: dict[int, list[Passo]] = {
    # até 20: a leitura vai direto (é a regressão que o PR #5 conserta)
    5: [(LEITURA, {"item": "0"})],
    # acima de 20: o grupo do servidor no catálogo não tem a escrita; o executor recusa o id
    # dela e roda a leitura pelo id
    25: [
        (BUSCAR, {"grupo": SERVIDOR}),
        (EXECUTOR, {"id": ALVO, "argumentos": ARGUMENTOS}),
        (EXECUTOR, {"id": LEITURA, "argumentos": {"item": "0"}}),
    ],
}


@pytest.mark.parametrize("quantidade", [25, 5])
async def test_rotina_sem_supervisao_le_mas_nao_oferece_a_escrita_mcp(
    ambiente_fase_b_arq: tuple[str, async_sessionmaker],
    monkeypatch: pytest.MonkeyPatch,
    quantidade: int,
) -> None:
    """Rotina (``sem_supervisao=True``): a leitura MCP roda e a rotina termina ``enviada``;
    ``delete_everything`` não é oferecida (nem no catálogo), não roda e não abre cartão."""
    import workers.rotinas as worker_rotinas

    roteiro = ROTEIRO_ROTINA[quantidade]
    url, fabrica = ambiente_fase_b_arq
    mcp = _instalar_mcp(monkeypatch, quantidade)
    registro = _roteirizar(monkeypatch, worker_rotinas, {"rotina"}, roteiro)
    email = _email(f"mcp-rotina-{quantidade}")
    async with httpx.AsyncClient(base_url=url, timeout=60) as cliente:
        auth = await _entrar(cliente, fabrica, email)
        usuario_id = await _usuario(fabrica, email)
        await _conectar(cliente, auth)

        criada = await cliente.post(
            "/v1/rotinas",
            headers=auth,
            json={"titulo": "Estoque", "pedido": "Confira o item 0.", "daqui_segundos": 1},
        )
        assert criada.status_code == 201, criada.text
        rotina_id = criada.json()["id"]

        async def terminou() -> list[dict]:
            resposta = await cliente.get(f"/v1/rotinas/{rotina_id}/execucoes", headers=auth)
            assert resposta.status_code == 200, resposta.text
            return [e for e in resposta.json() if e["concluida_em"]]

        (execucao,) = await _esperar(terminou, "a rotina não terminou")
        assert execucao["status"] == "enviada", execucao
        assert execucao["erro"] is None, execucao

        assert registro.terminou and registro.chamadas == roteiro, registro.chamadas
        assert mcp.leituras == ["get_item_0:0"], mcp.leituras
        respostas = registro.respostas
        assert len(respostas) == len(roteiro), respostas
        assert "Item 0: 3 unidades." in respostas[-1][1], respostas

        vistas = registro.vistas
        assert vistas, "a rotina não chamou o modelo roteirizado"
        assert ALVO not in vistas, sorted(vistas)
        if quantidade <= 20:
            assert LEITURA in vistas, sorted(vistas)  # direto, sem passar pelo catálogo
        else:
            assert LEITURA not in vistas and EXECUTOR in vistas, sorted(vistas)
            grupo = json.loads(respostas[0][1])
            assert grupo["grupo"] == SERVIDOR, grupo
            assert "delete_everything" not in grupo["nomes"], grupo
            assert sorted(grupo["nomes"]) == sorted(f"get_item_{i}" for i in range(24)), grupo
            assert respostas[1][1].startswith("Erro:"), respostas
            assert "desconhecida" in respostas[1][1], respostas

        assert mcp.efeitos == [], mcp.efeitos
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
    auth = await entrar(cliente, fabrica, _email(f"mcp-catalogo-{quantidade}"))
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
