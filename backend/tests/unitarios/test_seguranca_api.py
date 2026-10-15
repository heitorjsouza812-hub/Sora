"""Correções da auditoria do backend (nota "Segurança — Achados", itens API-01..10 e VAL-01..10).

Cada teste falharia no código anterior à correção; o ID do achado está no nome ou no docstring.
"""

import asyncio
import http.server
import inspect
import json
import threading
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import fakeredis
import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.busca import ler_pagina as lp
from app.core import contas, seguranca
from app.core.banco import obter_sessao
from app.core.config import Configuracao, obter_configuracao
from app.core.dependencias import obter_redis, usuario_atual
from app.eventos import sse
from app.eventos.streams import canal_conversa, canal_usuario
from app.llm import provedores
from app.llm.falso import ModeloFalsoEmProducao
from app.llm.provedores import (
    ClienteLiteLLMProtegido,
    ConfigProvedor,
    DestinoBloqueado,
    PoliticaRede,
    listar_modelos,
    parametros_litellm,
    validar_base_url,
)
from app.main import criar_aplicacao
from app.modelos.enumeracoes import TipoProvedor
from app.modelos.esquemas import (
    CadastroEntrada,
    ConversaCriacao,
    LoginEntrada,
    MensagemCriacao,
    ProvedorCriacao,
)

USUARIO = UUID("12121212-1212-4121-8121-121212121212")
CONVERSA = UUID("11111111-1111-4111-8111-111111111111")
PRODUCAO = PoliticaRede(producao=True, rede_local=False)
LOCAL = PoliticaRede(producao=False, rede_local=True)


@pytest.fixture
def config_limpa():
    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()


@pytest.fixture
async def redis():
    cliente = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield cliente
    await cliente.aclose()


# ------------------------------------------------- API-01: SSE não segura a sessão do banco


class _SessaoDona:
    async def execute(self, consulta: Any) -> "_SessaoDona":
        return self

    def scalar_one_or_none(self) -> UUID:
        return CONVERSA


async def _abrir_sse(app: Any, caminho: str, cabecalhos: list[tuple[bytes, bytes]]):
    """Dirige o ASGI à mão: (mensagens, evento do 1º corpo, desconectar, tarefa)."""
    recebidos: list[dict] = []
    desconectar, primeiro_corpo = asyncio.Event(), asyncio.Event()

    async def receive() -> dict:
        await desconectar.wait()
        return {"type": "http.disconnect"}

    async def send(mensagem: dict) -> None:
        recebidos.append(mensagem)
        if mensagem["type"] == "http.response.body" and mensagem.get("body"):
            primeiro_corpo.set()

    escopo = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": caminho, "raw_path": caminho.encode(), "query_string": b"",
        "root_path": "", "server": ("teste", 80), "client": ("1.2.3.4", 1),
        "headers": [(b"host", b"teste"), *cabecalhos],
    }  # fmt: skip
    tarefa = asyncio.create_task(app(escopo, receive, send))
    return recebidos, primeiro_corpo, desconectar, tarefa


async def test_api01_sessao_do_banco_fecha_antes_do_stream(redis) -> None:
    estado = {"fechou": False}

    async def sessao_dep():
        try:
            yield _SessaoDona()
        finally:
            estado["fechou"] = True

    await redis.xadd(canal_conversa(CONVERSA), {"event": "x", "data": "{}"})
    app = criar_aplicacao()
    app.dependency_overrides[usuario_atual] = lambda: USUARIO
    app.dependency_overrides[obter_sessao] = sessao_dep
    app.dependency_overrides[obter_redis] = lambda: redis

    recebidos, primeiro, desconectar, tarefa = await _abrir_sse(
        app, f"/v1/conversas/{CONVERSA}/eventos", [(b"last-event-id", b"0-0")]
    )
    await asyncio.wait_for(primeiro.wait(), 10)
    assert recebidos[0]["status"] == 200
    assert estado["fechou"], "a sessão ficou presa durante o stream (pool esgota)"
    desconectar.set()
    await asyncio.wait_for(tarefa, 10)


async def test_api01_limite_de_conexoes_sse_por_usuario(redis) -> None:
    vagas = [
        await sse.registrar_conexao(redis, USUARIO) for _ in range(sse.MAX_CONEXOES_POR_USUARIO)
    ]
    assert all(vagas)
    assert await sse.registrar_conexao(redis, USUARIO) is None
    assert await sse.registrar_conexao(redis, uuid4()) is not None  # outro usuário não é afetado
    await sse.encerrar_conexao(redis, USUARIO, vagas[0])
    assert await sse.registrar_conexao(redis, USUARIO) is not None


async def test_api01_rota_responde_429_com_o_limite_cheio(redis) -> None:
    from fastapi import HTTPException

    from app.api import eventos as rotas

    for _ in range(sse.MAX_CONEXOES_POR_USUARIO):
        await sse.registrar_conexao(redis, USUARIO)
    with pytest.raises(HTTPException) as erro:
        await rotas.eventos_do_usuario(USUARIO, redis)
    assert erro.value.status_code == 429
    assert "Retry-After" in (erro.value.headers or {})


async def test_api01_stream_encerrado_libera_a_vaga(redis) -> None:
    from app.api import eventos as rotas

    await redis.xadd(canal_usuario(USUARIO), {"event": "x", "data": "{}"})
    resposta = await rotas.eventos_do_usuario(USUARIO, redis, ultimo_evento_id="0-0")
    corpo = resposta.body_iterator
    await anext(corpo)  # type: ignore[call-overload]
    assert await redis.zcard(f"sse:conexoes:{USUARIO}") == 1
    await corpo.aclose()  # type: ignore[union-attr]
    assert await redis.zcard(f"sse:conexoes:{USUARIO}") == 0


# ------------------------------------------- API-08 / VAL-10: SSE fecha quando o token vence


async def test_api08_stream_termina_com_o_token_vencido(redis) -> None:
    canal = canal_usuario(USUARIO)
    await redis.xadd(canal, {"event": "x", "data": "{}"})
    recebidos = [
        m
        async for m in sse.gerar_sse(redis, canal, "0-0", bloquear_ms=10, expira_em=time.time() - 1)
    ]
    assert recebidos == []  # terminou sozinho, sem entregar o evento


async def test_api08_usuario_atual_guarda_o_exp_do_token() -> None:
    from fastapi.security import HTTPAuthorizationCredentials
    from starlette.requests import Request

    token = seguranca.criar_token_acesso({"sub": str(USUARIO)})
    requisicao = Request({"type": "http", "headers": [], "state": {}})
    credenciais = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert await usuario_atual(requisicao, credenciais) == USUARIO
    assert requisicao.state.token_expira_em > time.time()


# ------------------------------------------------------------------- API-02: SSRF no base_url


class _ServidorInterno:
    def __init__(self) -> None:
        corpo = json.dumps({"data": [{"id": "SEGREDO-INTERNO"}]}).encode()
        self.caminhos: list[str] = []
        dono = self

        class Tratador(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                dono.caminhos.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def log_message(self, *args: Any) -> None:
                pass

        self.servidor = http.server.HTTPServer(("127.0.0.1", 0), Tratador)
        self.porta = self.servidor.server_address[1]
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()


@pytest.fixture
def interno():
    servidor = _ServidorInterno()
    yield servidor
    servidor.servidor.shutdown()


async def test_api02_teste_de_chave_nao_alcanca_a_rede_interna(interno) -> None:
    sem_https = PoliticaRede(producao=False, rede_local=False)
    for tipo in (TipoProvedor.COMPATIVEL_OPENAI, TipoProvedor.OLLAMA):
        config = ConfigProvedor(
            tipo=tipo, api_key="sk-x", base_url=f"http://127.0.0.1:{interno.porta}/v1"
        )
        with pytest.raises(DestinoBloqueado):
            await listar_modelos(config, politica=sem_https)
    assert interno.caminhos == []


async def test_api02_dominio_que_resolve_para_ip_interno_e_barrado_na_conexao(interno) -> None:
    """Passa na validação de texto (é um domínio), mas o transporte seguro confere o IP."""
    sem_https = PoliticaRede(producao=False, rede_local=False)
    config = ConfigProvedor(
        tipo=TipoProvedor.COMPATIVEL_OPENAI, base_url=f"http://interno.exemplo:{interno.porta}"
    )

    async def resolve_interno(host: str, porta: int) -> list[str]:
        return ["127.0.0.1"]

    cliente = provedores.criar_cliente_listagem(sem_https, resolve_interno)
    with pytest.raises(DestinoBloqueado):
        await listar_modelos(config, cliente=cliente, politica=sem_https)
    await cliente.aclose()
    assert interno.caminhos == []


async def test_api02_rede_local_liberada_por_configuracao(interno) -> None:
    config = ConfigProvedor(
        tipo=TipoProvedor.COMPATIVEL_OPENAI, base_url=f"http://127.0.0.1:{interno.porta}/v1"
    )
    assert await listar_modelos(config, politica=LOCAL) == ["openai/SEGREDO-INTERNO"]


@pytest.mark.parametrize(
    ("base_url", "motivo"),
    [
        ("http://api.exemplo.com/v1", "https"),
        ("https://usuario:senha@api.exemplo.com", "usuário"),
        ("https://localhost:11434", "rede local"),
        ("https://127.0.0.1/v1", "rede local"),
        ("https://[::1]/v1", "rede local"),
        ("https://169.254.169.254/latest", "rede local"),
        ("https://10.0.0.5/v1", "rede local"),
        ("ftp://api.exemplo.com", "https://"),
        ("https://a.com/" + "x" * 2100, "2048"),
    ],
)
def test_api02_base_url_recusada_em_producao(base_url: str, motivo: str) -> None:
    with pytest.raises(DestinoBloqueado, match=motivo):
        validar_base_url(TipoProvedor.COMPATIVEL_OPENAI, base_url, PRODUCAO)


def _resolve_publico(host: str, porta: int) -> list[str]:
    return ["93.184.216.34"]


@pytest.fixture
def dns_publico(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem rede nos testes: todo domínio resolve para um IP público."""
    monkeypatch.setattr(provedores, "resolver_sincrono", _resolve_publico)


@pytest.mark.parametrize(
    ("host", "ips"),
    [
        ("localtest.me", ["127.0.0.1"]),
        ("redis", ["172.28.0.5"]),
        ("0x7f.1", ["127.0.0.1"]),
        ("misto.exemplo.com", ["93.184.216.34", "10.0.0.7"]),
        ("v6.exemplo.com", ["fd00:ec2::254"]),
    ],
)
def test_val14_nome_que_resolve_para_ip_interno_e_recusado(host: str, ips: list[str]) -> None:
    with pytest.raises(DestinoBloqueado, match="rede local"):
        validar_base_url(
            TipoProvedor.COMPATIVEL_OPENAI, f"https://{host}/v1", PRODUCAO, lambda h, p: ips
        )
    # com a flag de rede local, o mesmo endereço passa (Ollama/servidor na LAN)
    assert validar_base_url(TipoProvedor.COMPATIVEL_OPENAI, f"https://{host}/v1", LOCAL)


def test_val14_nome_que_nao_resolve_e_recusado() -> None:
    def sem_dns(host: str, porta: int) -> list[str]:
        return provedores.resolver_sincrono(host, porta)

    with pytest.raises(DestinoBloqueado, match="Não encontrei"):
        validar_base_url(
            TipoProvedor.COMPATIVEL_OPENAI, "https://nao-existe.invalid/v1", PRODUCAO, sem_dns
        )


def test_api02_base_url_aceita_e_tipos_oficiais_ignoram(dns_publico) -> None:
    assert (
        validar_base_url(TipoProvedor.COMPATIVEL_OPENAI, "https://api.exemplo.com/v1/", PRODUCAO)
        == "https://api.exemplo.com/v1"
    )
    for tipo in (TipoProvedor.OPENAI, TipoProvedor.ANTHROPIC, TipoProvedor.GOOGLE):
        config = ConfigProvedor(tipo=tipo, api_key="k", base_url="http://169.254.169.254")
        assert "api_base" not in parametros_litellm(config, PRODUCAO)


def test_api02_ollama_padrao_local_so_com_a_flag() -> None:
    with pytest.raises(DestinoBloqueado):
        parametros_litellm(ConfigProvedor(tipo=TipoProvedor.OLLAMA), PRODUCAO)
    assert parametros_litellm(ConfigProvedor(tipo=TipoProvedor.OLLAMA), LOCAL) == {
        "api_base": "http://localhost:11434"
    }


async def test_api02_cliente_litellm_confere_o_destino_antes_de_chamar() -> None:
    async def resolve_interno(host: str, porta: int) -> list[str]:
        return ["10.1.2.3"]

    cliente = ClienteLiteLLMProtegido(resolve_interno)
    with pytest.raises(DestinoBloqueado):
        await cliente.acompletion(model="openai/x", api_base="https://llm.exemplo.com", messages=[])
    with pytest.raises(DestinoBloqueado):
        cliente.completion(model="openai/x", api_base="https://127.0.0.1", messages=[])


def test_api02_fabrica_poe_o_cliente_protegido_em_producao(
    monkeypatch: pytest.MonkeyPatch, config_limpa, dns_publico
) -> None:
    from app.llm.fabrica import criar_chat_model

    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.delenv("SORA_MODELO_FALSO", raising=False)
    provedor = ConfigProvedor(
        tipo=TipoProvedor.COMPATIVEL_OPENAI, api_key="k", base_url="https://llm.exemplo.com/v1"
    )
    chat = criar_chat_model("openai/x", provedor)
    assert isinstance(chat.client, ClienteLiteLLMProtegido)  # type: ignore[attr-defined]


class _Redirecionador:
    """Servidor "público" que responde 307 para um servidor "interno" (ambos em 127.0.0.1)."""

    def __init__(self) -> None:
        self.acessos_internos: list[str] = []
        dono = self

        class Interno(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("content-length", 0)))
                dono.acessos_internos.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args: Any) -> None:
                pass

        self.interno = http.server.HTTPServer(("127.0.0.1", 0), Interno)
        destino = f"http://127.0.0.1:{self.interno.server_port}/interno"

        class Publico(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("content-length", 0)))
                self.send_response(307)
                self.send_header("location", destino)
                self.end_headers()

            def log_message(self, *args: Any) -> None:
                pass

        self.publico = http.server.HTTPServer(("127.0.0.1", 0), Publico)
        for servidor in (self.interno, self.publico):
            threading.Thread(target=servidor.serve_forever, daemon=True).start()

    def fechar(self) -> None:
        self.interno.shutdown()
        self.publico.shutdown()


@pytest.mark.parametrize("modelo", ["openai/x", "ollama/x"])
async def test_val14_chamada_nao_segue_redirecionamento(modelo: str) -> None:
    """Mesmo com a conexão liberada (resolvedor finge IP público e o transporte aceita),
    o 307 para a rede interna não é seguido."""
    servidores = _Redirecionador()

    async def tudo_publico(host: str, porta: int) -> list[str]:
        return ["127.0.0.1"] if porta == servidores.publico.server_port else ["10.9.9.9"]

    async def conferencia_ok(host: str, porta: int, resolver: Any = None) -> list[str]:
        return [host]

    cliente = ClienteLiteLLMProtegido(tudo_publico)
    original = provedores.ips_permitidos
    lp_original = lp.ips_permitidos
    provedores.ips_permitidos = conferencia_ok  # type: ignore[assignment]
    lp.ips_permitidos = conferencia_ok  # type: ignore[assignment]
    try:
        with pytest.raises(Exception):  # noqa: B017 (o 307 vira erro do provedor)
            await cliente.acompletion(
                model=modelo,
                api_base=f"http://127.0.0.1:{servidores.publico.server_port}",
                api_key="k",
                messages=[{"role": "user", "content": "oi"}],
                num_retries=0,
            )
    finally:
        provedores.ips_permitidos = original  # type: ignore[assignment]
        lp.ips_permitidos = lp_original  # type: ignore[assignment]
        servidores.fechar()
    assert servidores.acessos_internos == []


async def test_val14_conexao_confere_o_ip_de_novo() -> None:
    """DNS rebinding: a 1ª conferência vê IP público; na conexão o domínio já aponta para um
    servidor interno de verdade. O transporte seguro resolve de novo e recusa."""
    servidores = _Redirecionador()
    porta_interna = servidores.interno.server_port
    consultas: list[str] = []

    async def rebinding(host: str, porta: int) -> list[str]:
        consultas.append(host)
        return ["93.184.216.34"] if len(consultas) == 1 else ["127.0.0.1"]

    try:
        with pytest.raises(Exception) as erro:
            await ClienteLiteLLMProtegido(rebinding).acompletion(
                model="openai/x",
                api_base=f"http://rebinding.exemplo:{porta_interna}",
                api_key="k",
                messages=[{"role": "user", "content": "oi"}],
                num_retries=0,
            )
    finally:
        servidores.fechar()
    assert len(consultas) >= 2  # conferiu de novo na hora de conectar
    assert servidores.acessos_internos == []
    causas, atual = [], erro.value
    while atual is not None and len(causas) < 20:
        causas.append(type(atual).__name__)
        atual = atual.__cause__ or atual.__context__
    assert "EnderecoBloqueado" in causas


def _causas(erro: BaseException) -> list[str]:
    causas, atual = [], erro
    while atual is not None and len(causas) < 20:
        causas.append(type(atual).__name__)
        atual = atual.__cause__ or atual.__context__
    return causas


@pytest.mark.parametrize("modelo", ["openai/x", "ollama/x"])
def test_rodada7_chamada_sincrona_confere_o_ip_de_novo_na_conexao(modelo: str) -> None:
    """Resíduo do VAL-14 no caminho síncrono: a 1ª conferência vê IP público; na conexão o
    domínio já aponta para um servidor interno de verdade. Antes, o ``httpx.Client`` resolvia
    sozinho e conectava; agora o ``BackendSeguroSincrono`` resolve de novo e recusa."""
    servidores = _Redirecionador()
    porta_interna = servidores.interno.server_port
    consultas: list[str] = []

    def rebinding(host: str, porta: int) -> list[str]:
        consultas.append(host)
        return ["93.184.216.34"] if len(consultas) == 1 else ["127.0.0.1"]

    try:
        with pytest.raises(Exception) as erro:
            ClienteLiteLLMProtegido(resolver_sinc=rebinding).completion(
                model=modelo,
                api_base=f"http://rebinding.exemplo:{porta_interna}",
                api_key="k",
                messages=[{"role": "user", "content": "oi"}],
                num_retries=0,
            )
    finally:
        servidores.fechar()
    assert len(consultas) >= 2  # conferiu de novo na hora de conectar
    assert servidores.acessos_internos == []
    assert "EnderecoBloqueado" in _causas(erro.value)


@pytest.mark.parametrize("modelo", ["openai/x", "ollama/x"])
def test_rodada7_chamada_sincrona_nao_segue_redirecionamento(modelo: str) -> None:
    """Conexão liberada só para o servidor "público"; o 307 para o interno não é seguido."""
    servidores = _Redirecionador()
    porta_publica = servidores.publico.server_port

    def publico_liberado(host: str, porta: int, resolver: Any = None) -> list[str]:
        if porta != porta_publica:
            raise lp.EnderecoBloqueado("interno")
        return ["127.0.0.1"]

    original = provedores.ips_permitidos_sincrono
    provedores.ips_permitidos_sincrono = publico_liberado  # type: ignore[assignment]
    try:
        with pytest.raises(Exception):  # noqa: B017 (o 307 vira erro do provedor)
            ClienteLiteLLMProtegido().completion(
                model=modelo,
                api_base=f"http://publico.exemplo:{porta_publica}",
                api_key="k",
                messages=[{"role": "user", "content": "oi"}],
                num_retries=0,
            )
    finally:
        provedores.ips_permitidos_sincrono = original  # type: ignore[assignment]
        servidores.fechar()
    assert servidores.acessos_internos == []


def test_rodada7_transporte_sincrono_recusa_socket_local_e_ip_interno() -> None:
    backend = provedores.BackendSeguroSincrono(lambda h, p: ["10.0.0.1"])
    with pytest.raises(lp.EnderecoBloqueado):
        backend.connect_tcp("qualquer.exemplo", 443)
    with pytest.raises(lp.EnderecoBloqueado):
        backend.connect_tcp("169.254.169.254", 80)
    with pytest.raises(lp.EnderecoBloqueado):
        backend.connect_unix_socket("/var/run/docker.sock")
    with pytest.raises(lp.EnderecoBloqueado):  # um IP interno no meio já recusa tudo
        provedores.BackendSeguroSincrono(lambda h, p: ["93.184.216.34", "127.0.0.1"]).connect_tcp(
            "misto.exemplo", 443
        )


async def test_val14_provedor_desconhecido_com_api_base_e_recusado() -> None:
    with pytest.raises(DestinoBloqueado):
        await ClienteLiteLLMProtegido().acompletion(
            model="anthropic/x", api_base="https://93.184.216.34", messages=[]
        )


async def test_val14_cliente_http_seguro_nao_segue_redirect() -> None:
    http = provedores.cliente_http_seguro()
    assert http.follow_redirects is False
    assert http is provedores.cliente_http_seguro()  # um por laço


def test_api02_esquema_limita_base_url() -> None:
    with pytest.raises(ValidationError):
        ProvedorCriacao(tipo=TipoProvedor.COMPATIVEL_OPENAI, base_url="https://a.com/" + "x" * 2100)


# ------------------------------------------------- API-03 / VAL-10: exclusão completa (LGPD)


def test_api03_apaga_anexos_relativos_ao_volume_e_a_pasta_do_usuario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raiz, trabalho = tmp_path / "arquivos", tmp_path / "srv"
    trabalho.mkdir()
    salvo = f"{USUARIO}/anexos/foto.png"
    gerado = raiz / str(USUARIO) / "cadeias" / str(uuid4()) / "relatorio.md"
    for arquivo in (raiz / salvo, gerado):
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text("dados pessoais")
    vizinho = raiz / str(uuid4()) / "anexos" / "dele.png"
    vizinho.parent.mkdir(parents=True)
    vizinho.write_text("de outro usuário")
    fora = tmp_path / "fora.txt"
    fora.write_text("fora do volume")
    monkeypatch.chdir(trabalho)  # o caminho salvo não pode depender do diretório de trabalho

    contas.apagar_arquivos_do_usuario(raiz, USUARIO, [salvo, "../fora.txt"])

    assert not (raiz / salvo).exists()
    assert not (raiz / str(USUARIO)).exists()
    assert vizinho.exists() and fora.exists()


class _ResultadoLista:
    def __init__(self, itens: list[Any]) -> None:
        self._itens = itens

    def all(self) -> list[Any]:
        return self._itens


class _SessaoApagar:
    """Sessão falsa: responde às consultas de ``apagar_conta`` e registra os comandos."""

    def __init__(self, conversas: list[UUID], etapas: list[UUID]) -> None:
        self.usuario = type("U", (), {"senha_hash": seguranca.gerar_hash_senha("senha-certa-123")})
        self.conversas, self.etapas = conversas, etapas
        self.comandos: list[str] = []

    async def get(self, _modelo: Any, _id: UUID) -> Any:
        return self.usuario

    async def scalars(self, consulta: Any) -> _ResultadoLista:
        sql = str(consulta)
        if "anexos.caminho" in sql:
            return _ResultadoLista([])
        if "FROM etapas" in sql:
            return _ResultadoLista(self.etapas)
        return _ResultadoLista(self.conversas)

    async def scalar(self, _consulta: Any, _params: Any = None) -> str:
        return "existe"  # to_regclass: as tabelas do checkpointer existem

    async def execute(self, comando: Any, params: Any = None) -> None:
        self.comandos.append(f"{comando} {params or ''}")

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.comandos.append("COMMIT")


async def test_api03_apagar_conta_limpa_checkpoints_e_streams(redis, tmp_path: Path) -> None:
    conversa, etapa = uuid4(), uuid4()
    for canal in (canal_conversa(conversa), canal_usuario(USUARIO)):
        await redis.xadd(canal, {"event": "x", "data": "{}"})
    sessao = _SessaoApagar([conversa], [etapa])

    await contas.apagar_conta(
        sessao,  # type: ignore[arg-type]
        USUARIO,
        "senha-certa-123",
        redis=redis,
        raiz_arquivos=tmp_path,
    )

    assert not await redis.exists(canal_conversa(conversa), canal_usuario(USUARIO))
    checkpoints = [c for c in sessao.comandos if "thread_id" in c]
    assert len(checkpoints) == len(contas.TABELAS_CHECKPOINT)
    assert all(f"conversa:{conversa}" in c and f"etapa:{etapa}" in c for c in checkpoints)


# -------------------------------------------------- API-04 / VAL-09: limite de login por falha


class _Usuario:
    id = USUARIO
    senha_hash = seguranca.gerar_hash_senha("senha-correta-da-vitima")


class _SessaoLogin:
    async def scalar(self, _consulta: Any) -> _Usuario:
        return _Usuario()

    def add(self, _obj: Any) -> None:
        pass

    async def flush(self) -> None:
        pass


async def _entrar(redis, senha: str, ip: str) -> Any:
    entrada = LoginEntrada(email="vitima@exemplo.com", senha=senha)
    return await contas.entrar(_SessaoLogin(), redis, entrada, "web", ip, None)  # type: ignore[arg-type]


async def test_api04_atacante_de_outros_ips_nao_tranca_a_vitima(redis) -> None:
    for n in range(10):
        with pytest.raises(contas.ErroCredenciais):
            await _entrar(redis, "chute-errado", f"10.0.0.{n}")
    renovacao, acesso = await _entrar(redis, "senha-correta-da-vitima", "200.1.1.1")
    assert renovacao and acesso


async def test_api04_login_certo_nao_conta_no_limite(redis) -> None:
    for _ in range(8):
        await _entrar(redis, "senha-correta-da-vitima", "1.1.1.1")


async def test_api04_cinco_falhas_do_mesmo_ip_bloqueiam_aquele_ip(redis) -> None:
    for _ in range(5):
        with pytest.raises(contas.ErroCredenciais):
            await _entrar(redis, "chute-errado", "6.6.6.6")
    with pytest.raises(contas.ErroLimite):
        await _entrar(redis, "senha-correta-da-vitima", "6.6.6.6")


# --------------------------------------------------- API-06 / VAL-09: renovação com trava


def test_api06_renovacao_trava_a_linha_da_sessao() -> None:
    sql = str(
        contas.consulta_sessao_do_token("h", travar=True).compile(dialect=postgresql.dialect())
    )
    assert "FOR UPDATE" in sql


async def test_api06_renovar_usa_a_consulta_com_trava() -> None:
    capturadas: list[str] = []

    class Sessao:
        async def scalar(self, consulta: Any) -> None:
            capturadas.append(str(consulta.compile(dialect=postgresql.dialect())))

    with pytest.raises(contas.ErroCredenciais):
        await contas.renovar(Sessao(), "token-qualquer")  # type: ignore[arg-type]
    assert "FOR UPDATE" in capturadas[0]


# ------------------------------------------------------ VAL-08: cadastro não enumera e-mails


async def test_val08_sem_convite_valido_nao_revela_email_existente(redis) -> None:
    class Sessao:
        async def execute(self, _comando: Any) -> Any:
            return type("R", (), {"first": lambda self: None})()  # convite não consumido

        async def scalar(self, _consulta: Any) -> UUID:
            return USUARIO  # o e-mail já existe

    dados = CadastroEntrada(
        nome="X", email="ana@exemplo.com", senha="uma-senha-bem-longa", convite="chute"
    )
    with pytest.raises(contas.ErroConvite):
        await contas.cadastrar(Sessao(), redis, dados, "1.2.3.4")  # type: ignore[arg-type]


# --------------------------------------------------------- API-07 / VAL-06/07: entradas


def test_api07_textos_e_listas_com_limite() -> None:
    with pytest.raises(ValidationError):
        ConversaCriacao(texto="a" * 20_001)
    with pytest.raises(ValidationError):
        MensagemCriacao(texto="ok", anexos=[uuid4() for _ in range(21)])
    with pytest.raises(ValidationError):
        CadastroEntrada(nome="", email="a@b.com", senha="uma-senha-bem-longa")
    with pytest.raises(ValidationError):
        CadastroEntrada(nome="a" * 121, email="a@b.com", senha="uma-senha-bem-longa")
    assert CadastroEntrada(nome="Ana", email="ana@exemplo.com.br", senha="uma-senha-bem-longa")


# --------------------------------------------------------- API-05: extração fora do laço


async def test_api05_extracao_lenta_nao_trava_o_laco(monkeypatch: pytest.MonkeyPatch) -> None:
    def lenta(conteudo: bytes, tipo: str, url: str) -> tuple[None, str]:
        time.sleep(0.6)
        return None, "texto"

    monkeypatch.setattr(lp, "extrair_texto", lenta)
    batidas = 0

    async def coracao() -> None:
        nonlocal batidas
        while True:
            await asyncio.sleep(0.05)
            batidas += 1

    tarefa = asyncio.create_task(coracao())
    with pytest.raises(lp.ErroLeitura, match="demorou"):
        await lp.extrair_texto_sem_travar(b"x", "text/plain", "", prazo=0.3)
    tarefa.cancel()
    assert batidas >= 3  # o laço continuou rodando durante a extração


def test_api05_html_acima_do_limite_e_recusado_sem_processar() -> None:
    html = b"<!doctype html><p>" + b"a" * (lp.MAX_BYTES_HTML + 1)
    inicio = time.perf_counter()
    with pytest.raises(lp.ErroLeitura, match="2 MB"):
        lp.extrair_texto(html, "text/html", "https://exemplo.com")
    assert time.perf_counter() - inicio < 1


# ---------------------------------------------- API-09 / VAL-02..05: configuração segura


def test_api09_cors_de_producao_sem_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("APP_URL", "https://sora.exemplo.com.br/")
    monkeypatch.delenv("CORS_ORIGENS", raising=False)
    config = Configuracao(_env_file=None)  # type: ignore[call-arg]
    assert config.origens_cors == [
        "https://sora.exemplo.com.br",
        "http://tauri.localhost",
        "tauri://localhost",
    ]
    monkeypatch.setenv("CORS_ORIGENS", "https://sora.exemplo.com.br,http://localhost:5173")
    with pytest.raises(ValidationError):
        Configuracao(_env_file=None)  # type: ignore[call-arg]


def test_api09_desenvolvimento_mantem_os_padroes_locais(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "desenvolvimento")
    monkeypatch.setenv("JWT_SEGREDO", "curto")
    monkeypatch.setenv("PERMITIR_PROVEDOR_REDE_LOCAL", "")  # vazio = não definido
    config = Configuracao(_env_file=None)  # type: ignore[call-arg]
    assert "http://localhost:5173" in config.origens_cors
    assert config.rede_local_permitida is True


def test_api09_producao_proibe_rede_local_por_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "producao")
    assert Configuracao(_env_file=None).rede_local_permitida is False  # type: ignore[call-arg]
    monkeypatch.setenv("PERMITIR_PROVEDOR_REDE_LOCAL", "1")
    assert Configuracao(_env_file=None).rede_local_permitida is True  # type: ignore[call-arg]


def test_api09_producao_recusa_jwt_de_exemplo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("JWT_SEGREDO", "troque-este-valor-por-um-segredo-aleatorio")
    with pytest.raises(ValidationError):
        Configuracao(_env_file=None)  # type: ignore[call-arg]


def test_val02_sim_liga_o_modelo_falso_na_configuracao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SORA_MODELO_FALSO", "sim")
    assert Configuracao(_env_file=None).sora_modelo_falso is True  # type: ignore[call-arg]


async def test_val02_worker_nao_sobe_com_modelo_falso_em_producao(
    monkeypatch: pytest.MonkeyPatch, config_limpa
) -> None:
    from workers.configuracao import ao_iniciar

    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    obter_configuracao.cache_clear()  # o import do worker já leu a configuração do teste
    with pytest.raises(ModeloFalsoEmProducao):
        await ao_iniciar({})


def test_val03_cookie_sai_secure_sem_ambiente(
    monkeypatch: pytest.MonkeyPatch, config_limpa
) -> None:
    from fastapi import Response

    from app.api.auth import _responder_tokens

    monkeypatch.delenv("AMBIENTE", raising=False)
    resposta = Response()
    _responder_tokens(resposta, "web", "renovacao", "acesso")
    assert "secure" in resposta.headers["set-cookie"].lower()


# ----------------------------------------------------------------- API-10: entregas por dono


@pytest.mark.parametrize("nome", ["versoes_da_conversa", "entregas_da_versao", "aprovar_versao"])
def test_api10_funcoes_de_entrega_exigem_usuario_id(nome: str) -> None:
    from app.orquestrador import entregas

    parametro = inspect.signature(getattr(entregas, nome)).parameters.get("usuario_id")
    assert parametro is not None
    assert parametro.kind is inspect.Parameter.KEYWORD_ONLY
    assert parametro.default is inspect.Parameter.empty


# ---------------------------------------------------------- VAL-01: integração sem daemon


def test_val01_docker_parado_pula_a_integracao(monkeypatch: pytest.MonkeyPatch) -> None:
    import docker

    from tests.integracao.conftest import docker_disponivel

    monkeypatch.setattr("shutil.which", lambda _nome: "docker")

    def sem_daemon() -> Any:
        raise docker.errors.DockerException("daemon parado")

    monkeypatch.setattr(docker, "from_env", sem_daemon)
    disponivel, motivo = docker_disponivel()
    assert not disponivel and "não está respondendo" in motivo
