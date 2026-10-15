"""Camada llm: custo por chamada, fábrica ChatLiteLLM e classificação de erros (sem rede)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import litellm
import pytest
from langchain_core.messages import AIMessage

from app.core.config import obter_configuracao
from app.llm.custo import (
    PrecoModelo,
    UsoTokens,
    calcular_custo,
    extrair_uso,
    inicio_do_mes,
    precos_litellm,
)
from app.llm.fabrica import criar_chat_model, criar_modelos_na_ordem
from app.llm.provedores import (
    ConfigProvedor,
    ErroProvedor,
    parametros_litellm,
)
from app.llm.troca import (
    EstadoSaude,
    MotivoTroca,
    classificar_erro,
    deve_trocar,
    montar_middleware_de_troca,
    registrar_falha,
    registrar_sucesso,
)
from app.modelos.enumeracoes import TipoProvedor


@pytest.fixture(autouse=True)
def _config_limpa():
    obter_configuracao.cache_clear()
    yield
    obter_configuracao.cache_clear()


# ------------------------------------------------------------------ custo


def test_custo_usa_o_preco_do_catalogo_por_milhao_de_tokens() -> None:
    preco = PrecoModelo(entrada=Decimal(3), saida=Decimal(15))
    uso = UsoTokens(tokens_entrada=2_000, tokens_saida=1_000)
    assert calcular_custo("qualquer/modelo", uso, preco) == Decimal("0.021000")


def test_custo_sem_preco_em_lugar_nenhum_e_zero() -> None:
    uso = UsoTokens(tokens_entrada=10, tokens_saida=10)
    assert calcular_custo("modelo/que-nao-existe-em-lugar-nenhum", uso) == Decimal(0)


def test_custo_cai_no_mapa_do_litellm_quando_o_catalogo_nao_tem_preco(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        litellm.model_cost,
        "teste/modelo",
        {"input_cost_per_token": 0.000002, "output_cost_per_token": 0.00001},
    )
    preco = precos_litellm("teste/modelo")
    assert preco == PrecoModelo(entrada=Decimal(2), saida=Decimal(10))
    uso = UsoTokens(tokens_entrada=1_000_000, tokens_saida=500_000)
    assert calcular_custo("teste/modelo", uso, PrecoModelo()) == Decimal("7.000000")


def test_extrai_uso_do_usage_metadata_e_do_uso_cru_do_provedor() -> None:
    a = AIMessage(
        content="x", usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}
    )
    assert extrair_uso(a) == UsoTokens(tokens_entrada=7, tokens_saida=3)
    b = AIMessage(
        content="x", response_metadata={"token_usage": {"prompt_tokens": 5, "completion_tokens": 2}}
    )
    assert extrair_uso(b) == UsoTokens(tokens_entrada=5, tokens_saida=2)
    assert extrair_uso(AIMessage(content="x")) == UsoTokens(tokens_entrada=0, tokens_saida=0)


def test_inicio_do_mes_e_utc() -> None:
    agora = datetime(2026, 10, 14, 23, 59, tzinfo=UTC)
    assert inicio_do_mes(agora) == datetime(2026, 10, 1, tzinfo=UTC)


# ------------------------------------------------------------------ fábrica


def test_criar_chat_model_nao_usa_rede_e_nao_vaza_a_chave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SORA_MODELO_FALSO", raising=False)
    config = ConfigProvedor(tipo=TipoProvedor.GROQ, api_key="gsk_segredo_de_teste")
    chat = criar_chat_model("groq/openai/gpt-oss-20b", config, papel="sistema1", max_tokens=100)
    assert type(chat).__name__ == "ChatLiteLLM"
    assert chat.model == "groq/openai/gpt-oss-20b"
    assert chat.max_retries == 0
    assert "gsk_segredo_de_teste" not in repr(chat)
    assert "gsk_segredo_de_teste" not in repr(config)


def test_com_modelo_falso_ligado_a_fabrica_devolve_o_falso(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    obter_configuracao.cache_clear()
    config = ConfigProvedor(tipo=TipoProvedor.GROQ)
    chat = criar_chat_model("groq/x", config, papel="redator")
    assert chat._llm_type == "modelo-falso-sora"


def test_criar_modelos_na_ordem_mantem_a_ordem(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SORA_MODELO_FALSO", raising=False)
    config = ConfigProvedor(tipo=TipoProvedor.OPENAI, api_key="k")
    modelos = criar_modelos_na_ordem([("openai/a", config), ("openai/b", config)])
    assert [m.model for m in modelos] == ["openai/a", "openai/b"]


def test_parametros_litellm_por_tipo_de_provedor() -> None:
    assert parametros_litellm(ConfigProvedor(tipo=TipoProvedor.GROQ, api_key="k")) == {
        "api_key": "k"
    }
    assert parametros_litellm(ConfigProvedor(tipo=TipoProvedor.OLLAMA)) == {
        "api_base": "http://localhost:11434"
    }
    compat = ConfigProvedor(tipo=TipoProvedor.COMPATIVEL_OPENAI, base_url="http://x/v1/")
    assert parametros_litellm(compat) == {"api_base": "http://x/v1", "api_key": "sem-chave"}
    with pytest.raises(ErroProvedor):
        parametros_litellm(ConfigProvedor(tipo=TipoProvedor.COMPATIVEL_OPENAI))


# ------------------------------------------------------------------ erros da troca de provedor


def erro_http(status: int) -> httpx.HTTPStatusError:
    pedido = httpx.Request("POST", "http://provedor")
    return httpx.HTTPStatusError(
        "erro", request=pedido, response=httpx.Response(status, request=pedido)
    )


@pytest.mark.parametrize(
    ("erro", "motivo"),
    [
        (erro_http(429), MotivoTroca.LIMITE_DE_TAXA),
        (erro_http(500), MotivoTroca.ERRO_DO_SERVIDOR),
        (erro_http(503), MotivoTroca.ERRO_DO_SERVIDOR),
        (httpx.ReadTimeout("lento"), MotivoTroca.PRAZO),
        (TimeoutError(), MotivoTroca.PRAZO),
        (
            litellm.RateLimitError("limite", llm_provider="groq", model="m"),
            MotivoTroca.LIMITE_DE_TAXA,
        ),
        (
            litellm.InternalServerError("falhou", llm_provider="groq", model="m"),
            MotivoTroca.ERRO_DO_SERVIDOR,
        ),
        (litellm.Timeout("lento", model="m", llm_provider="groq"), MotivoTroca.PRAZO),
    ],
)
def test_erros_que_justificam_trocar_de_modelo(erro: BaseException, motivo: MotivoTroca) -> None:
    assert classificar_erro(erro) is motivo
    assert deve_trocar(erro)


@pytest.mark.parametrize(
    "erro",
    [
        erro_http(400),
        erro_http(401),
        erro_http(403),
        ValueError("bug"),
        litellm.AuthenticationError("chave ruim", llm_provider="groq", model="m"),
        litellm.BadRequestError("pedido ruim", model="m", llm_provider="groq"),
    ],
)
def test_erros_que_nao_justificam_troca(erro: BaseException) -> None:
    assert classificar_erro(erro) is None
    assert not deve_trocar(erro)


def test_segue_a_cadeia_de_causas() -> None:
    try:
        try:
            raise erro_http(429)
        except httpx.HTTPStatusError as interno:
            raise RuntimeError("embrulhado") from interno
    except RuntimeError as externo:
        assert classificar_erro(externo) is MotivoTroca.LIMITE_DE_TAXA


class ArmazemEmMemoria:
    def __init__(self) -> None:
        self.estados: dict[UUID, EstadoSaude] = {}

    async def obter(self, provedor_id: UUID) -> EstadoSaude:
        return self.estados.get(provedor_id, EstadoSaude(provedor_id=provedor_id))

    async def salvar(self, estado: EstadoSaude) -> None:
        self.estados[estado.provedor_id] = estado


async def test_tres_falhas_seguidas_pausam_o_provedor_por_cinco_minutos() -> None:
    armazem, pid = ArmazemEmMemoria(), uuid4()
    agora = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    for _ in range(2):
        estado = await registrar_falha(
            armazem, pid, falhas_para_pausar=3, pausa_minutos=5, agora=agora
        )
        assert estado.pausado_ate is None
    estado = await registrar_falha(armazem, pid, falhas_para_pausar=3, pausa_minutos=5, agora=agora)
    assert estado.falhas_seguidas == 3
    assert estado.pausado_ate == agora + timedelta(minutes=5)


async def test_sucesso_zera_falhas_e_pausa() -> None:
    armazem, pid = ArmazemEmMemoria(), uuid4()
    for _ in range(3):
        await registrar_falha(armazem, pid, falhas_para_pausar=3, pausa_minutos=5)
    estado = await registrar_sucesso(armazem, pid)
    assert estado.falhas_seguidas == 0
    assert estado.pausado_ate is None


def test_middleware_de_troca_monta_reserva_aviso_e_nova_tentativa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    obter_configuracao.cache_clear()
    config = ConfigProvedor(tipo=TipoProvedor.GROQ)
    modelos = criar_modelos_na_ordem([("groq/a", config), ("groq/b", config)], papel="redator")

    async def ao_trocar(_evento) -> None: ...

    nomes = [type(m).__name__ for m in montar_middleware_de_troca(modelos, ao_trocar=ao_trocar)]
    assert nomes == ["ModelFallbackMiddleware", "NotificadorDeTroca", "ModelRetryMiddleware"]
    assert [type(m).__name__ for m in montar_middleware_de_troca(modelos[:1])] == [
        "ModelRetryMiddleware"
    ]
    with pytest.raises(ValueError):
        montar_middleware_de_troca([])
