"""Limite do provedor (Âncora, rodada 4): 429 com retry-after espera e repete o mesmo modelo,
"Request too large" enxuga o pedido, e o erro final fala em PT-BR. O provedor é um servidor HTTP
local que imita a Groq (formato OpenAI); sem rede e sem modelo falso."""

from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from app.agentes.middleware.encerra_depois_de_falar import deve_encerrar
from app.agentes.middleware.limite_provedor import MiddlewareLimiteDoProvedor
from app.llm.limite import (
    MENSAGEM_LIMITE,
    ErroLimiteDoProvedor,
    enxugar,
    espera_com_teto,
    espera_pedida,
    limite_do_provedor,
)
from app.llm.troca import classificar_erro, montar_middleware_de_troca


class FalsaGroq:
    """Servidor local: cada POST consome a próxima resposta do roteiro (a última se repete)."""

    def __init__(self, roteiro: list[dict[str, Any]]) -> None:
        self.roteiro = roteiro
        self.corpos: list[dict[str, Any]] = []
        dono = self

        class Tratador(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                tamanho = int(self.headers.get("content-length", 0))
                dono.corpos.append(json.loads(self.rfile.read(tamanho)))
                passo = dono.roteiro[min(len(dono.corpos) - 1, len(dono.roteiro) - 1)]
                corpo = json.dumps(passo["corpo"]).encode()
                self.send_response(passo["status"])
                self.send_header("content-type", "application/json")
                for chave, valor in passo.get("cabecalhos", {}).items():
                    self.send_header(chave, valor)
                self.send_header("content-length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def log_message(self, *args: Any) -> None:
                pass

        self.servidor = HTTPServer(("127.0.0.1", 0), Tratador)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.servidor.server_port}/v1"

    def fechar(self) -> None:
        self.servidor.shutdown()


def _resposta(texto: str = "ok", chamada: dict | None = None) -> dict[str, Any]:
    mensagem: dict[str, Any] = {"role": "assistant", "content": texto}
    if chamada:
        mensagem = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": chamada["nome"], "arguments": json.dumps(chamada["args"])},
                }
            ],
        }
    return {
        "status": 200,
        "corpo": {
            "id": "x",
            "object": "chat.completion",
            "created": 1,
            "model": "qwen",
            "choices": [{"index": 0, "message": mensagem, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
        },
    }


def _limite(mensagem: str, espera: str | None = None) -> dict[str, Any]:
    return {
        "status": 429,
        "cabecalhos": {"retry-after": espera} if espera else {},
        "corpo": {"error": {"message": mensagem, "type": "tokens", "code": "rate_limit_exceeded"}},
    }


def _modelo(url: str):
    from langchain_litellm import ChatLiteLLM

    return ChatLiteLLM(
        model="openai/qwen",
        api_base=url,
        api_key="x",
        max_retries=0,
        model_kwargs={"max_retries": 0},
    )


@pytest.fixture
def groq():
    criados: list[FalsaGroq] = []

    def nova(roteiro: list[dict[str, Any]]) -> FalsaGroq:
        falsa = FalsaGroq(roteiro)
        criados.append(falsa)
        return falsa

    yield nova
    for falsa in criados:
        falsa.fechar()


@tool
def navegador_observar() -> str:
    """Lê a página."""
    return "arvore " * 2000


async def _rodar(modelos, middleware, ferramentas=()):
    agente = create_agent(
        model=modelos[0], tools=list(ferramentas), middleware=middleware, name="teste"
    )
    return await agente.ainvoke({"messages": [HumanMessage("oi")]})


async def test_429_com_retry_after_espera_e_repete_o_mesmo_modelo(groq) -> None:
    principal = groq(
        [
            _limite("Rate limit reached ... Please try again in 26s.", "26"),
            _limite("Rate limit reached ... Please try again in 1.5s."),
            _resposta("pronto"),
        ]
    )
    reserva = groq([_resposta("da reserva")])
    esperas: list[float] = []
    avisos: list[int] = []

    async def dormir(segundos: float) -> None:
        esperas.append(segundos)

    async def avisar(segundos: int) -> None:
        avisos.append(segundos)

    modelos = [_modelo(principal.url), _modelo(reserva.url)]
    middleware = [
        *montar_middleware_de_troca(modelos, espera_inicial_s=0.01),
        MiddlewareLimiteDoProvedor(ao_esperar=avisar, dormir=dormir),
    ]
    resultado = await _rodar(modelos, middleware)

    assert resultado["messages"][-1].content == "pronto"
    assert len(principal.corpos) == 3
    assert reserva.corpos == []  # não trocou de modelo
    assert esperas == [26.5, 2.0]
    assert avisos == [26, 2]


async def test_limite_que_nao_cede_tenta_o_proximo_modelo_so_depois_das_esperas(groq) -> None:
    principal = groq([_limite("Rate limit reached ... Please try again in 20s.")])
    reserva = groq([_resposta("da reserva")])
    esperas: list[float] = []

    async def dormir(segundos: float) -> None:
        esperas.append(segundos)

    modelos = [_modelo(principal.url), _modelo(reserva.url)]
    middleware = [
        *montar_middleware_de_troca(modelos, espera_inicial_s=0.01),
        MiddlewareLimiteDoProvedor(dormir=dormir),
    ]
    resultado = await _rodar(modelos, middleware)

    assert len(principal.corpos) == 4  # 1 + 3 esperas no mesmo modelo, antes de qualquer troca
    assert esperas == [20.5, 20.5, 20.5]
    assert resultado["messages"][-1].content == "da reserva"


async def test_limite_em_todos_os_modelos_vira_mensagem_clara(groq) -> None:
    principal = groq([_limite("Rate limit reached ... Please try again in 20s.")])
    reserva = groq([_limite("Rate limit reached ... Please try again in 20s.")])

    async def dormir(segundos: float) -> None:
        return None

    modelos = [_modelo(principal.url), _modelo(reserva.url)]
    middleware = [
        *montar_middleware_de_troca(modelos, espera_inicial_s=0.01),
        MiddlewareLimiteDoProvedor(dormir=dormir),
    ]
    with pytest.raises(ErroLimiteDoProvedor) as info:
        await _rodar(modelos, middleware)

    assert len(principal.corpos) == 4 and len(reserva.corpos) == 4
    assert MENSAGEM_LIMITE in str(info.value)
    assert limite_do_provedor(info.value)
    assert classificar_erro(info.value) is None


async def test_espera_acima_do_teto_desiste_na_hora(groq) -> None:
    principal = groq([_limite("Rate limit reached ... Please try again in 12m3s.")])

    async def dormir(segundos: float) -> None:
        raise AssertionError("não devia esperar tanto")

    with pytest.raises(ErroLimiteDoProvedor):
        await _rodar([_modelo(principal.url)], [MiddlewareLimiteDoProvedor(dormir=dormir)])
    assert len(principal.corpos) == 1


async def test_pedido_grande_demais_repete_com_resultados_antigos_resumidos(groq) -> None:
    grande = _limite(
        "Request too large for model `qwen` on input tokens per minute (ITPM): Limit 7000, "
        "Requested 7650, please reduce your message size and try again."
    )
    servidor = groq(
        [
            _resposta(chamada={"nome": "navegador_observar", "args": {}}),
            _resposta(chamada={"nome": "navegador_observar", "args": {}}),
            grande,  # a terceira chamada tem duas árvores no histórico: grande demais
            _resposta("resumo"),
        ]
    )

    async def dormir(segundos: float) -> None:
        raise AssertionError("pedido grande não espera")

    resultado = await _rodar(
        [_modelo(servidor.url)],
        [MiddlewareLimiteDoProvedor(dormir=dormir)],
        [navegador_observar],
    )
    assert resultado["messages"][-1].content == "resumo"
    assert len(servidor.corpos) == 4

    def tamanho(corpo: dict[str, Any]) -> int:
        return len(json.dumps(corpo["messages"]))

    # a repetição vai bem menor que a recusada e a árvore antiga virou resumo
    assert tamanho(servidor.corpos[3]) < tamanho(servidor.corpos[2]) / 2
    assert "resultado antigo resumido" in json.dumps(servidor.corpos[3]["messages"])


async def test_pedido_grande_que_continua_grande_vira_mensagem_clara(groq) -> None:
    servidor = groq([_limite("Request too large for model `qwen` ... reduce your message size")])
    with pytest.raises(ErroLimiteDoProvedor):
        await _rodar([_modelo(servidor.url)], [MiddlewareLimiteDoProvedor()])
    assert len(servidor.corpos) == 2  # original + enxuta


def test_espera_pedida_le_cabecalho_e_texto() -> None:
    assert espera_pedida(Exception("Please try again in 26s.")) == 26
    assert espera_pedida(Exception("try again in 1m3.5s. Visit")) == 63.5
    assert espera_pedida(Exception("Please try again in 250ms.")) == 0.25
    assert espera_pedida(Exception("sem dica")) is None
    assert espera_com_teto(Exception("sem dica")) == 5.0
    assert espera_com_teto(Exception("try again in 2m")) is None


def test_enxugar_nao_mexe_na_lista_original() -> None:
    mensagens = [
        HumanMessage("a"),
        ToolMessage(content="x" * 5000, name="navegador_observar", tool_call_id="1"),
        ToolMessage(content="y" * 5000, name="navegador_observar", tool_call_id="2"),
        ToolMessage(content="z" * 5000, name="buscar_web", tool_call_id="3"),
    ]
    nivel1 = enxugar(mensagens, 1)
    assert len(nivel1[1].content) < 400 and len(nivel1[2].content) == 5000
    assert len(nivel1[3].content) == 5000
    nivel2 = enxugar(mensagens, 2)
    assert len(nivel2[2].content) < 400 and len(nivel2[3].content) < 3100
    assert len(mensagens[1].content) == 5000


def test_primeira_chamada_do_pesquisador_com_navegador_fica_abaixo_de_4000_tokens() -> None:
    """Medida registrada: prompt + esquemas das ferramentas, 1 token ≈ 4 caracteres."""
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from app.agentes.ancora import navegador_preguicoso
    from app.agentes.montagem import (
        ContextoAgente,
        montar_prompt_de_sistema,
        nomes_das_ferramentas,
    )
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.registro import criar_ferramentas

    contexto = ContextoAgente(
        usuario_id=uuid.uuid4(),
        agente_id=uuid.uuid4(),
        conversa_id=uuid.uuid4(),
        papel="pesquisador",
        cadeia_id=uuid.uuid4(),
        etapa_id=uuid.uuid4(),
        valores_do_prompt={
            "nome": "Atlas",
            "objetivo": "Pesquisar domínios reservados da IANA",
            "papel": "pesquisador",
            "pronto_quando": "resumo entregue",
            "resultados_anteriores": "nenhum",
            "tarefa": "Abra iana.org/domains/reserved e resuma",
        },
    )
    ferramentas = navegador_preguicoso(
        criar_ferramentas(
            nomes_das_ferramentas(contexto),
            ContextoFerramenta(
                usuario_id=contexto.usuario_id,
                agente_id=contexto.agente_id,
                conversa_id=contexto.conversa_id,
                cadeia_id=contexto.cadeia_id,
                etapa_id=contexto.etapa_id,
            ),
        ),
        contexto,
    )
    nomes = {f.name for f in ferramentas}
    diretas = {"navegador_abrir", "navegador_observar", "navegador_acao", "navegador_procurar"}
    assert diretas <= nomes
    assert "navegador_esperar" not in nomes and "navegador_executar_ferramenta" in nomes
    caracteres = len(montar_prompt_de_sistema(contexto)) + sum(
        len(json.dumps(convert_to_openai_tool(f), ensure_ascii=False)) for f in ferramentas
    )
    tokens = caracteres // 4
    print(f"primeira chamada do pesquisador com navegador: ~{tokens} tokens de entrada")
    assert tokens < 4000, tokens


def test_falar_sozinho_depois_de_ferramenta_encerra_o_turno() -> None:
    def chamada(nome: str, i: str) -> AIMessage:
        return AIMessage(content="", tool_calls=[{"name": nome, "args": {}, "id": i}])

    anuncio = [
        HumanMessage("guarde"),
        chamada("falar", "1"),
        ToolMessage("ok", name="falar", tool_call_id="1"),
    ]
    assert deve_encerrar(anuncio) is False  # primeiro falar é aviso: segue para a ferramenta
    relato = [
        *anuncio,
        chamada("lembrar", "2"),
        ToolMessage("ok", name="lembrar", tool_call_id="2"),
        chamada("falar", "3"),
        ToolMessage("ok", name="falar", tool_call_id="3"),
    ]
    assert deve_encerrar(relato) is True
    assert deve_encerrar(relato[:-2]) is False  # acabou de voltar a ferramenta: fala ainda


# ---------------------------------------------------------------- rodada 6


def _navegador_escondido():
    from app.agentes.ancora import SINONIMOS_DO_NAVEGADOR, _com_sinonimos
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.catalogo_preguicoso import CatalogoFerramentas
    from app.ferramentas.registro import criar_ferramentas

    nomes = list(SINONIMOS_DO_NAVEGADOR)
    ferramentas = criar_ferramentas(
        nomes,
        ContextoFerramenta(
            usuario_id=uuid.uuid4(), agente_id=uuid.uuid4(), conversa_id=uuid.uuid4()
        ),
    )
    return CatalogoFerramentas([_com_sinonimos(f) for f in ferramentas], "navegador"), nomes


def test_toda_ferramenta_escondida_do_navegador_e_encontravel() -> None:
    catalogo, nomes = _navegador_escondido()
    for nome in nomes:
        sufixo = nome.removeprefix("navegador_")
        for consulta, grupo in ((sufixo, "navegador"), (sufixo, ""), (nome, "navegador")):
            achados = [f["id"] for f in catalogo.buscar(consulta, grupo)["ferramentas"]]
            assert nome in achados, (nome, consulta, grupo, achados)
    # sem consulta, o grupo lista todas
    assert sorted(catalogo.buscar("", "navegador")["nomes"]) == sorted(nomes)


def test_busca_aceita_flexao_sinonimo_e_acento() -> None:
    catalogo, _ = _navegador_escondido()

    def achou(consulta: str, nome: str) -> bool:
        return nome in [f["id"] for f in catalogo.buscar(consulta, "navegador")["ferramentas"]]

    assert achou("captura", "navegador_capturar")
    assert achou("screenshot", "navegador_capturar")
    assert achou("aguardar", "navegador_esperar")
    assert achou("aguardar carregar", "navegador_esperar")
    assert achou("teclado", "navegador_tecla")
    assert achou("ações em lote", "navegador_lote")
    # grupo que não existe não esconde a ferramenta
    assert achou("capturar", "navegador_capturar") and "navegador_capturar" in [
        f["id"] for f in catalogo.buscar("capturar", "grupo-errado")["ferramentas"]
    ]


async def test_juiz_espera_o_limite_do_plano_antes_de_cair_no_cartao() -> None:
    from app.revisor.juiz import AcaoProposta, avaliar_acao

    class Limite(Exception):
        status_code = 429

        def __str__(self) -> str:
            return "Rate limit reached ... Please try again in 3s."

    tentativas = 0
    esperas: list[float] = []

    async def modelo(sistema: str, prompt: str) -> str:
        nonlocal tentativas
        tentativas += 1
        if tentativas < 3:
            raise Limite
        return (
            '{"dano": "nenhum", "quem_recebe": null, "destino": "nao_externo", '
            '"decisao": "PERMITIR", "motivo": "pedido pelo usuario"}'
        )

    async def dormir(segundos: float) -> None:
        esperas.append(segundos)

    veredito = await avaliar_acao(
        modelo,
        AcaoProposta(ferramenta="navegador_acao", argumentos={"acao": "clicar"}),
        ["clique em Publicar"],
        dormir=dormir,
    )
    assert veredito.decisao.value == "PERMITIR"
    assert tentativas == 3 and esperas == [3.5, 3.5]


async def test_juiz_que_nao_se_recupera_diz_que_nao_conseguiu_avaliar() -> None:
    from app.revisor.juiz import AcaoProposta, avaliar_acao

    class Limite(Exception):
        status_code = 429

        def __str__(self) -> str:
            return "Rate limit reached ... Please try again in 3s."

    async def modelo(sistema: str, prompt: str) -> str:
        raise Limite

    async def dormir(segundos: float) -> None:
        return None

    veredito = await avaliar_acao(
        modelo,
        AcaoProposta(ferramenta="navegador_acao", argumentos={}),
        [],
        dormir=dormir,
    )
    assert veredito.decisao.value == "BLOQUEAR"
    assert "Não consegui avaliar o risco agora; a decisão fica com você." in veredito.motivo


def test_enxugar_mantem_inteira_a_ultima_leitura_de_cada_ferramenta_do_navegador() -> None:
    mensagens = [
        HumanMessage("a"),
        ToolMessage(content="o" * 5000, name="navegador_observar", tool_call_id="1"),
        ToolMessage(content="p" * 5000, name="navegador_procurar", tool_call_id="2"),
        ToolMessage(content="q" * 5000, name="navegador_observar", tool_call_id="3"),
    ]
    saida = enxugar(mensagens, 1)
    assert len(saida[1].content) < 400  # observação antiga repetida encolhe
    assert len(saida[2].content) == 5000  # a última procura segue inteira
    assert len(saida[3].content) == 5000  # a última observação segue inteira
