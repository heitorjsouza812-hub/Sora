"""Seletor do campo de mensagem (Âncora-9): níveis de raciocínio por família, modos de permissão,
bloqueios absolutos, aviso do modelo escolhido e o PC do usuário no modo total.

A parte com banco (preferências da conversa, do grupo e do bot, isolamento, validação, worker com
modelo fixo e aprovação automática gravada) está em
``tests/integracao/test_ancora9_seletor_modelo.py``.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.computador.pc_usuario_canal import CanalPc
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.llm.raciocinio import (
    NIVEIS,
    e_rapido,
    niveis_de_raciocinio,
    nivel_mais_proximo,
    parametros_de_raciocinio,
)
from app.preferencias_conversa import (
    ModeloEscolhidoIndisponivel,
    marcar_escolhido,
    modelo_escolhido,
    texto_da_falha,
)
from app.revisor import decisoes
from app.revisor.decisoes import aprova_sozinho, bloqueio_absoluto, risco_baixo
from tests.unitarios.test_pc_usuario import (
    AppFalso,
    CartoesFalsos,
    _conectar,
    _erro,
    _ok,
    _pc,
    _resolvida,
)

MODOS = ("perguntar", "automatico", "total")

# ---------- raciocínio por família ----------


@pytest.mark.parametrize(
    ("modelo", "niveis"),
    [
        ("groq/openai/gpt-oss-20b", ["baixo", "medio", "alto"]),
        ("groq/openai/gpt-oss-120b", ["baixo", "medio", "alto"]),
        ("openrouter/openai/gpt-oss-120b", ["baixo", "medio", "alto"]),
        ("openai/o3-mini", ["baixo", "medio", "alto"]),
        ("openai/o4-mini-2025-04-16", ["baixo", "medio", "alto"]),
        ("o1", ["baixo", "medio", "alto"]),
        ("openai/gpt-5.6-terra", ["baixo", "medio", "alto"]),
        ("xai/grok-3-mini", ["baixo", "alto"]),
        ("anthropic/claude-sonnet-4-20250514", list(NIVEIS)),
        ("anthropic/claude-3-7-sonnet-20250219", list(NIVEIS)),
        ("anthropic/claude-opus-5-5", list(NIVEIS)),
        ("anthropic/claude-haiku-5-5", list(NIVEIS)),
        ("gemini/gemini-2.5-flash", list(NIVEIS)),
        ("gemini/gemini-3.1-pro-preview", list(NIVEIS)),
        # sem raciocínio ajustável
        ("anthropic/claude-3-5-sonnet-20241022", []),
        ("anthropic/claude-3-haiku-20240307", []),
        ("gemini/gemini-2.0-flash", []),
        ("openai/gpt-4o", []),
        ("groq/llama-3.3-70b-versatile", []),
        ("groq/llama-3.1-8b-instant", []),
        ("deepseek/deepseek-v4-pro", []),
        ("mistral/mistral-large-latest", []),
        ("ollama/qwen3:8b", []),
        ("openrouter/anthropic/claude-sonnet-4", []),
        ("xai/grok-4.7", []),
    ],
)
def test_niveis_por_familia(modelo: str, niveis: list[str]) -> None:
    assert niveis_de_raciocinio(modelo) == niveis


def test_parametros_do_litellm_por_familia() -> None:
    gpt = parametros_de_raciocinio("groq/openai/gpt-oss-20b", "medio")
    assert gpt is not None and gpt.extras == {"reasoning_effort": "medium"}
    assert gpt.temperatura is None and gpt.max_tokens_minimo is None
    assert parametros_de_raciocinio("openai/o3-mini", "baixo").extras == {  # type: ignore[union-attr]
        "reasoning_effort": "low"
    }
    claude = parametros_de_raciocinio("anthropic/claude-sonnet-4-20250514", "maximo")
    assert claude is not None
    assert claude.extras == {"thinking": {"type": "enabled", "budget_tokens": 32_000}}
    assert claude.temperatura == 1.0 and claude.max_tokens_minimo > 32_000  # type: ignore[operator]
    gemini = parametros_de_raciocinio("gemini/gemini-2.5-flash", "baixo")
    assert gemini is not None
    assert gemini.extras == {"thinking": {"type": "enabled", "budget_tokens": 1_024}}
    # nível que o modelo não aceita, auto e modelo sem raciocínio: nada muda
    assert parametros_de_raciocinio("groq/openai/gpt-oss-20b", "maximo") is None
    assert parametros_de_raciocinio("groq/openai/gpt-oss-20b", "auto") is None
    assert parametros_de_raciocinio("groq/llama-3.3-70b-versatile", "alto") is None


def test_nivel_mais_proximo_no_automatico() -> None:
    assert nivel_mais_proximo("groq/openai/gpt-oss-20b", "maximo") == "alto"
    assert nivel_mais_proximo("groq/openai/gpt-oss-20b", "extra_alto") == "alto"
    assert nivel_mais_proximo("groq/openai/gpt-oss-20b", "baixo") == "baixo"
    assert nivel_mais_proximo("xai/grok-3-mini", "medio") == "alto"  # empate: o mais alto
    assert nivel_mais_proximo("anthropic/claude-opus-5-5", "extra_alto") == "extra_alto"
    assert nivel_mais_proximo("groq/llama-3.3-70b-versatile", "alto") is None
    assert nivel_mais_proximo("groq/openai/gpt-oss-20b", "auto") is None


def test_modelo_rapido() -> None:
    assert e_rapido("N1", None)
    assert e_rapido("N2", 500)
    assert not e_rapido("N3", 100)
    assert not e_rapido("especial", None)


def test_fabrica_aplica_o_raciocinio(monkeypatch) -> None:
    monkeypatch.delenv("SORA_MODELO_FALSO", raising=False)
    from app.llm import fabrica
    from app.llm.provedores import ConfigProvedor
    from app.modelos.enumeracoes import TipoProvedor

    monkeypatch.setattr(fabrica, "modelo_falso_ativo", lambda: False)
    anthropic = ConfigProvedor(provedor_id=uuid4(), tipo=TipoProvedor.ANTHROPIC)
    chat = fabrica.criar_chat_model(
        "anthropic/claude-sonnet-4-20250514", anthropic, raciocinio="alto", max_tokens=1000
    )
    assert chat.model_kwargs["thinking"] == {"type": "enabled", "budget_tokens": 10_000}
    assert chat.temperature == 1.0 and chat.max_tokens > 10_000
    groq = ConfigProvedor(provedor_id=uuid4(), tipo=TipoProvedor.GROQ)
    chat = fabrica.criar_chat_model("groq/openai/gpt-oss-20b", groq, raciocinio="baixo")
    assert chat.model_kwargs == {"max_retries": 0, "reasoning_effort": "low"}
    assert chat.temperature == 0.0
    sem = fabrica.criar_chat_model("groq/openai/gpt-oss-20b", groq)
    assert sem.model_kwargs == {"max_retries": 0}


# ---------- aviso do modelo escolhido ----------


class _Chat:
    def __init__(self) -> None:
        self.metadata: dict[str, Any] | None = None


def _erro_http(status: int) -> Exception:
    resposta = httpx.Response(status, request=httpx.Request("POST", "https://x"))
    return httpx.HTTPStatusError("falhou", request=resposta.request, response=resposta)


def test_aviso_do_modelo_escolhido_sem_troca() -> None:
    chat = _Chat()
    assert modelo_escolhido([chat]) is None
    assert texto_da_falha([chat], RuntimeError("x")) is None  # automático: texto de sempre
    marcar_escolhido(chat, "groq/openai/gpt-oss-120b", ["ferramentas"])
    assert modelo_escolhido([chat]) == "groq/openai/gpt-oss-120b"
    limite = texto_da_falha([chat], _erro_http(429))
    assert limite is not None and "groq/openai/gpt-oss-120b" in limite
    assert "limite" in limite and "Não troquei de modelo sozinho" in limite
    fora = texto_da_falha([chat], _erro_http(503))
    assert fora is not None and "fora do ar" in fora
    chave = texto_da_falha([chat], _erro_http(401))
    assert chave is not None and "chave" in chave
    sumiu = ModeloEscolhidoIndisponivel("O modelo X não está disponível.")
    assert texto_da_falha([], sumiu) == "O modelo X não está disponível."


# ---------- modos de permissão ----------


def _acao(ferramenta: str, **argumentos: Any) -> dict[str, Any]:
    return {"ferramenta": ferramenta, "argumentos": argumentos}


BLOQUEIOS_ABSOLUTOS = {
    "senha digitada no computador": _acao(
        "computador_agir", alvo="virtual", acoes=[{"tipo": "digitar", "texto": "Tr0ub4dor&3x"}]
    ),
    "senha digitada no PC": _acao(
        "computador_agir", alvo="pc_usuario", acoes=[{"tipo": "digitar", "texto": "S3nh@F0rte!"}]
    ),
    "campo IsPassword": _acao("navegador_acao", ref="@s1:e2", acao="digitar", IsPassword=True),
    "campo de senha no navegador": _acao("navegador_lote", passos=[{"tipo": "fill", "senha": "x"}]),
    "chave de API digitada": _acao(
        "computador_agir",
        acoes=[{"tipo": "digitar", "texto": "sk-ant-api03-abcdefghijklmnopqrstu"}],
    ),
    "programa bloqueado (gerenciador de senha)": {
        "tipo": "pc_programa",
        "ferramenta": "computador_pc_programa",
        "argumentos": {"programa": "keepass.exe"},
        "condicao": {"programa": "keepass.exe"},
    },
    "programa bloqueado (UAC)": _acao("computador_pc_programa", programa="consent.exe"),
    "programa bloqueado (terminal)": _acao("computador_pc_programa", programa="cmd.exe"),
    "programa bloqueado (a própria Sora)": _acao("computador_pc_programa", programa="sora.exe"),
    "alerta de programa bloqueado": {"tipo": "pc_bloqueio", "ferramenta": "computador_agir"},
    "envio pelo WhatsApp da empresa": _acao("mcp__whatsapp__send_message", para="+55", texto="oi"),
    "envio pelo Slack da empresa": _acao(
        "conectores_executar_ferramenta", id="mcp__slack__post_message", argumentos={}
    ),
    "resposta pelo canal da empresa": _acao("canais_empresa_responder", texto="oi"),
    "bot mudar as próprias instruções": _acao("propor_instrucoes", instrucoes="novas"),
    "bot mudar habilidade": _acao("atualizar_habilidade", nome="x"),
    "bot apagar habilidade": _acao("apagar_habilidade", nome="x"),
    "aplicar sugestão de melhoria": {"tipo": "sugestao_melhoria", "ferramenta": "aplicar"},
    "pagamento por conector": _acao("mcp__stripe__create_payment", valor=10),
    "compra por nome": _acao("mcp__loja__comprar_produto", sku="1"),
    "clique em Finalizar compra": _acao("navegador_acao", ref="@s1:e9", nome="Finalizar compra"),
    "checkout na URL": _acao("navegador_agir", url="https://loja.com/checkout?x=1"),
    "pix": _acao("navegador_lote", passos=[{"tipo": "clicar", "rotulo": "Pagar com Pix"}]),
}


@pytest.mark.parametrize("caso", sorted(BLOQUEIOS_ABSOLUTOS))
@pytest.mark.parametrize("modo", MODOS)
def test_bloqueio_absoluto_nunca_passa_sozinho(caso: str, modo: str) -> None:
    acao = BLOQUEIOS_ABSOLUTOS[caso]
    assert bloqueio_absoluto(acao) is not None, caso
    for login in (True, False):
        assert not aprova_sozinho(modo, acao, perfil_tem_login=login), (caso, modo)
    assert not risco_baixo(acao, perfil_tem_login=False)


def test_programas_bloqueados_do_pc_estao_todos_cobertos() -> None:
    from app.computador.pc_usuario import PROGRAMAS_BLOQUEADOS

    for programa in PROGRAMAS_BLOQUEADOS:
        acao = _acao("computador_pc_programa", programa=programa)
        assert bloqueio_absoluto(acao) == "programa bloqueado para bots", programa
        assert not aprova_sozinho("total", acao)


@pytest.mark.parametrize(
    "ferramenta",
    ["criar_agente", "propor_instrucoes", "esquecer_memoria", "criar_habilidade",
     "atualizar_habilidade", "apagar_habilidade", "adicionar_servidor_mcp"],
)  # fmt: skip
def test_cartao_fixo_nunca_passa_sozinho(ferramenta: str) -> None:
    for modo in MODOS:
        assert not aprova_sozinho(modo, _acao(ferramenta)), (ferramenta, modo)


def test_rotina_sem_supervisao_nunca_passa_sozinha() -> None:
    acao = _acao("executar_comando", comando="ls")
    assert aprova_sozinho("total", acao)
    assert not aprova_sozinho("total", acao, sem_supervisao=True)
    assert not aprova_sozinho("automatico", _acao("mcp__x__list_items"), sem_supervisao=True)


RISCO_BAIXO = {
    "leitura por conector": _acao(
        "conectores_executar_ferramenta", id="mcp__notion__search_pages", argumentos={}
    ),
    "navegador sem login": _acao("navegador_acao", ref="@s1:e3", acao="clicar"),
    "computador virtual sem abrir programa": _acao(
        "computador_agir",
        alvo="virtual",
        acoes=[
            {"tipo": "clicar", "x": 3, "y": 4},
            {"tipo": "digitar", "texto": "relatório mensal"},
        ],
    ),
}
RISCO_NAO_BAIXO = {
    "comando": _acao("executar_comando", comando="rm -rf /tmp/x"),
    "conector que escreve": _acao("mcp__notion__create_page", titulo="x"),
    "e-mail": _acao("mcp__gmail__send_email", para="a@b.com"),
    "computador virtual abrindo programa": _acao(
        "computador_agir", alvo="virtual", acoes=[{"tipo": "abrir", "programa": "navegador"}]
    ),
    "PC do usuário": _acao("computador_agir", alvo="pc_usuario", acoes=[{"tipo": "clicar"}]),
}


@pytest.mark.parametrize("caso", sorted(RISCO_BAIXO))
def test_automatico_aprova_o_risco_baixo(caso: str) -> None:
    acao = RISCO_BAIXO[caso]
    assert not aprova_sozinho("perguntar", acao, perfil_tem_login=False)
    assert aprova_sozinho("automatico", acao, perfil_tem_login=False), caso
    assert aprova_sozinho("total", acao, perfil_tem_login=False), caso


def test_navegador_com_login_nao_e_risco_baixo() -> None:
    acao = RISCO_BAIXO["navegador sem login"]
    assert not aprova_sozinho("automatico", acao, perfil_tem_login=True)
    assert aprova_sozinho("total", acao, perfil_tem_login=True)


@pytest.mark.parametrize("caso", sorted(RISCO_NAO_BAIXO))
def test_automatico_pergunta_o_resto_e_total_aprova(caso: str) -> None:
    acao = RISCO_NAO_BAIXO[caso]
    assert not aprova_sozinho("perguntar", acao)
    assert not aprova_sozinho("automatico", acao, perfil_tem_login=False), caso
    assert aprova_sozinho("total", acao), caso


def test_modo_desconhecido_vale_perguntar() -> None:
    assert not aprova_sozinho("qualquer", RISCO_BAIXO["leitura por conector"])
    assert decisoes.MODOS_PERMISSAO == ("perguntar", "automatico", "total")


def test_texto_do_passo() -> None:
    texto = decisoes.texto_aprovado_automaticamente("total", "Executar comando")
    assert texto == "Aprovado automaticamente (modo total): Executar comando"
    assert "modo automático" in decisoes.texto_aprovado_automaticamente("automatico", "x")


# ---------- conferir_acao com o modo da conversa ----------


class _Cartao(Exception):
    pass


@pytest.fixture
def execucao(monkeypatch):
    from app.revisor import execucao

    registro: dict[str, list[Any]] = {"registros": [], "eventos": [], "juiz": []}

    async def nenhum(*_a, **_k):
        return None

    async def registrar(_contexto, proposta, resumo, aprovacao_id):
        registro["registros"].append((proposta.ferramenta, resumo, aprovacao_id))

    async def emitir(_contexto, evento):
        registro["eventos"].append(evento)

    async def abrir_cartao(*_a, **_k):
        raise _Cartao()

    async def regra(*_a, **_k):
        return False

    async def juiz(_chamar, proposta, _pedidos):
        from app.revisor.juiz import bloqueio

        registro["juiz"].append(proposta.ferramenta)
        return bloqueio("na dúvida, pergunta")

    async def pedidos(_contexto):
        return []

    monkeypatch.setattr(execucao, "_cartao_existente", nenhum)
    monkeypatch.setattr(execucao, "_registrar", registrar)
    monkeypatch.setattr(execucao, "emitir", emitir)
    monkeypatch.setattr(execucao, "_abrir_cartao", abrir_cartao)
    monkeypatch.setattr(execucao, "_pedidos_do_usuario", pedidos)
    monkeypatch.setattr("app.revisor.acoes.regra_permite", regra)
    monkeypatch.setattr("app.revisor.juiz.avaliar_acao", juiz)
    return execucao, registro


def _contexto(permissao: str, **extra: Any) -> ContextoFerramenta:
    return ContextoFerramenta(
        usuario_id=uuid4(),
        agente_id=uuid4(),
        conversa_id=uuid4(),
        etapa_painel=uuid4(),
        permissao=permissao,
        **extra,
    )


async def test_total_aprova_e_mostra_o_passo(execucao) -> None:
    modulo, registro = execucao
    contexto = _contexto("total")
    resultado = await modulo.conferir_acao(
        "executar_comando", {"comando": "ls"}, contexto, chamada_id="c1"
    )
    assert resultado is None
    assert registro["juiz"] == []  # nem passou pelo juiz
    [(ferramenta, resumo, aprovacao)] = registro["registros"]
    assert ferramenta == "executar_comando" and aprovacao is None
    assert resumo.startswith("Aprovado automaticamente (modo total)")
    [evento] = registro["eventos"]
    assert evento.evento == "passo" and evento.etapa_id == contexto.etapa_painel
    assert evento.texto.startswith("Aprovado automaticamente (modo total)")
    assert evento.resultado == {"aprovacao": "automatica", "modo": "total"}


async def test_perguntar_continua_abrindo_o_cartao(execucao) -> None:
    modulo, registro = execucao
    with pytest.raises(_Cartao):
        await modulo.conferir_acao(
            "executar_comando", {"comando": "ls"}, _contexto("perguntar"), chamada_id="c1"
        )
    assert registro["juiz"] == ["executar_comando"] and registro["eventos"] == []


async def test_automatico_pergunta_o_que_nao_e_risco_baixo(execucao) -> None:
    modulo, registro = execucao
    with pytest.raises(_Cartao):
        await modulo.conferir_acao(
            "executar_comando", {"comando": "ls"}, _contexto("automatico"), chamada_id="c1"
        )
    assert registro["eventos"] == []


async def test_automatico_aprova_computador_virtual(execucao) -> None:
    modulo, registro = execucao
    argumentos = {"alvo": "virtual", "acoes": [{"tipo": "clicar", "x": 1, "y": 2}]}
    assert (
        await modulo.conferir_acao(
            "computador_agir", argumentos, _contexto("automatico"), chamada_id="c1"
        )
        is None
    )
    assert "modo automático" in registro["eventos"][0].texto


@pytest.mark.parametrize("modo", ["automatico", "total"])
async def test_senha_no_total_ainda_pede_cartao(execucao, modo: str) -> None:
    modulo, registro = execucao
    argumentos = {"alvo": "virtual", "acoes": [{"tipo": "digitar", "texto": "Tr0ub4dor&3x"}]}
    with pytest.raises(_Cartao):
        await modulo.conferir_acao("computador_agir", argumentos, _contexto(modo), chamada_id="c")
    assert registro["eventos"] == []


async def test_cartao_fixo_no_total_ainda_pede_cartao(execucao) -> None:
    modulo, registro = execucao
    with pytest.raises(_Cartao):
        await modulo.conferir_acao(
            "esquecer_memoria", {"memoria_id": "x"}, _contexto("total"), chamada_id="c"
        )
    assert registro["eventos"] == []


async def test_rotina_sem_supervisao_ignora_o_modo(execucao) -> None:
    modulo, registro = execucao
    resultado = await modulo.conferir_acao(
        "executar_comando",
        {"comando": "ls"},
        _contexto("total", sem_supervisao=True),
        chamada_id="c",
    )
    assert resultado == modulo.SEM_SUPERVISAO and registro["eventos"] == []
    assert await modulo.modo_de_permissao(_contexto("total", sem_supervisao=True)) == "perguntar"


# ---------- PC do usuário (C3) no modo total ----------


@pytest.fixture
def redis():
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis(decode_responses=True)


async def test_pc_no_total_libera_o_programa_sem_cartao(redis) -> None:
    cartoes = CartoesFalsos()
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    avisos: list[tuple[str, str]] = []

    async def avisar(modo: str, resumo: str) -> None:
        avisos.append((modo, resumo))

    computador.modo_permissao = "total"
    computador.ao_aprovar_sozinho = avisar

    def responder(comando: dict[str, Any]) -> dict[str, Any]:
        if "notepad.exe" in comando["dados"]["programas_permitidos"]:
            return _ok()
        return _erro("programa_nao_permitido", programa="Notepad.exe", titulo="Sem título")

    with AppFalso(CanalPc(redis), usuario_id, sessao_id, responder):
        await computador.agir(_resolvida(tipo="digitar", texto="Lista de compras"))
    assert cartoes.abertos == []  # nenhum cartão
    assert avisos == [("total", "usar notepad.exe (“Sem título”) no seu computador")]


@pytest.mark.parametrize("modo", MODOS)
async def test_pc_programa_bloqueado_em_qualquer_modo(redis, modo: str) -> None:
    cartoes = CartoesFalsos()
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    computador.modo_permissao = modo
    with AppFalso(
        CanalPc(redis),
        usuario_id,
        sessao_id,
        lambda _c: _erro("programa_nao_permitido", programa="C:\\x\\KeePass.exe"),
    ):
        with pytest.raises(ErroFerramenta, match="bloqueado para bots"):
            await computador.agir(_resolvida(tipo="clicar", x=1, y=1))
    assert cartoes.abertos == []


async def test_pc_no_automatico_continua_pedindo_o_cartao(redis) -> None:
    cartoes = CartoesFalsos()
    bot = uuid4()
    usuario_id, sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    computador.modo_permissao = "automatico"

    async def decidir() -> None:
        await cartoes.aberto.wait()
        cartoes.situacao[cartoes.abertos[0][0]] = "permitida"

    def responder(comando: dict[str, Any]) -> dict[str, Any]:
        if "mspaint.exe" in comando["dados"]["programas_permitidos"]:
            return _ok()
        return _erro("programa_nao_permitido", programa="mspaint.exe")

    with AppFalso(CanalPc(redis), usuario_id, sessao_id, responder):
        decisao = asyncio.create_task(decidir())
        await computador.agir(_resolvida(tipo="clicar", x=1, y=1))
        await decisao
    assert len(cartoes.abertos) == 1


async def test_pc_no_total_senha_continua_recusada(redis) -> None:
    from app.computador.pc_usuario import SENHA

    cartoes = CartoesFalsos()
    bot = uuid4()
    usuario_id, _sessao_id, provedor = await _conectar(redis, cartoes, bot)
    computador = await _pc(provedor, usuario_id, bot)
    computador.modo_permissao = "total"
    with pytest.raises(ErroFerramenta, match=SENHA[:20]):
        await computador.agir(_resolvida(tipo="digitar", texto="S3nh@F0rte!"))
