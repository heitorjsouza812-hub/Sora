"""Rodada 3 do Vigia: commit antes da resposta, limite atômico, apagar conta e worker."""

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient

from app.core import banco, contas, seguranca
from app.core.config import obter_configuracao
from app.core.redis import verificar_limite
from app.llm.falso import ModeloFalsoEmProducao
from app.main import criar_aplicacao
from app.modelos.esquemas import LoginEntrada


@pytest.fixture
async def redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


# ------------------------------------------------------------ 1. commit antes da resposta


class _SessaoRegistradora:
    def __init__(self, eventos: list[str]) -> None:
        self.eventos = eventos

    async def commit(self) -> None:
        self.eventos.append("commit")

    async def rollback(self) -> None:
        self.eventos.append("rollback")

    async def __aenter__(self) -> "_SessaoRegistradora":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


async def test_commit_acontece_antes_de_a_resposta_comecar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eventos: list[str] = []
    monkeypatch.setattr(banco, "fabrica_sessoes", lambda: lambda: _SessaoRegistradora(eventos))
    aplicacao = criar_aplicacao()

    async def app_observado(escopo: Any, receber: Any, enviar: Any) -> None:
        async def enviar_observado(mensagem: Any) -> None:
            if mensagem["type"] == "http.response.start":
                eventos.append("resposta")
            await enviar(mensagem)

        await aplicacao(escopo, receber, enviar_observado)

    async with AsyncClient(transport=ASGITransport(app=app_observado), base_url="http://t") as c:
        resposta = await c.post("/v1/auth/sair", json={})
    assert resposta.status_code == 204
    assert eventos == ["commit", "resposta"]


class _SessaoApagar:
    def __init__(self, eventos: list[str]) -> None:
        self.eventos = eventos
        self.usuario = type("U", (), {"senha_hash": seguranca.gerar_hash_senha("senha-certa-123")})

    async def get(self, *_: Any) -> Any:
        return self.usuario

    async def scalars(self, _consulta: Any) -> Any:
        return type("R", (), {"all": lambda _s: []})()

    async def scalar(self, *_: Any) -> None:
        return None

    async def execute(self, *_: Any) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.eventos.append("commit")


async def test_apagar_conta_so_apaga_arquivos_depois_do_commit(
    redis: FakeAsyncRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    eventos: list[str] = []
    monkeypatch.setattr(
        contas, "apagar_arquivos_do_usuario", lambda *_a, **_k: eventos.append("arquivos")
    )
    await contas.apagar_conta(
        _SessaoApagar(eventos),  # type: ignore[arg-type]
        uuid4(),
        "senha-certa-123",
        redis=redis,
        raiz_arquivos=tmp_path,
    )
    assert eventos == ["commit", "arquivos"]


async def test_apagar_conta_com_falha_no_banco_nao_apaga_arquivos(
    redis: FakeAsyncRedis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    apagados: list[str] = []
    monkeypatch.setattr(
        contas, "apagar_arquivos_do_usuario", lambda *_a, **_k: apagados.append("x")
    )
    sessao = _SessaoApagar([])

    async def falhar() -> None:
        raise RuntimeError("banco caiu")

    sessao.commit = falhar  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await contas.apagar_conta(
            sessao,  # type: ignore[arg-type]
            uuid4(),
            "senha-certa-123",
            redis=redis,
            raiz_arquivos=tmp_path,
        )
    assert apagados == []


# ------------------------------------------------------------ 7. limite atômico


async def test_limite_nao_deixa_passar_alem_do_maximo_em_chamadas_simultaneas(
    redis: FakeAsyncRedis,
) -> None:
    resultados = await asyncio.gather(*(verificar_limite(redis, "k", 3, 60) for _ in range(20)))
    assert resultados.count(0) == 3
    assert await redis.zcard("limite:k") == 3


# ------------------------------------------------------------ 15. apagar conta com limite


async def test_apagar_conta_limita_tentativas_de_senha(
    redis: FakeAsyncRedis, tmp_path: Path
) -> None:
    usuario_id = uuid4()
    for _ in range(contas.LIMITE_APAGAR_CONTA[0]):
        with pytest.raises(contas.ErroSenhaIncorreta):
            await contas.apagar_conta(
                _SessaoApagar([]),  # type: ignore[arg-type]
                usuario_id,
                "errada-errada",
                redis=redis,
                raiz_arquivos=tmp_path,
            )
    with pytest.raises(contas.ErroLimite) as erro:
        await contas.apagar_conta(
            _SessaoApagar([]),  # type: ignore[arg-type]
            usuario_id,
            "senha-certa-123",
            redis=redis,
            raiz_arquivos=tmp_path,
        )
    assert int(erro.value.headers["Retry-After"]) > 0


# ------------------------------------------------------------ login simultâneo


async def test_login_simultaneo_errado_respeita_o_limite(redis: FakeAsyncRedis) -> None:
    class Sessao:
        async def scalar(self, _c: Any) -> None:
            return None

    entrada = LoginEntrada(email="x@exemplo.com", senha="chute-errado-1")
    saidas = await asyncio.gather(
        *(
            contas.entrar(Sessao(), redis, entrada, "web", "9.9.9.9", None)  # type: ignore[arg-type]
            for _ in range(12)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(s, contas.ErroCredenciais) for s in saidas) == 5
    assert sum(isinstance(s, contas.ErroLimite) for s in saidas) == 7


# ------------------------------------------------------------ 10. worker


async def test_worker_recusa_modelo_falso_em_producao(monkeypatch: pytest.MonkeyPatch) -> None:
    from workers.configuracao import ao_iniciar

    obter_configuracao.cache_clear()
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    try:
        with pytest.raises(ModeloFalsoEmProducao):
            await ao_iniciar({})
    finally:
        obter_configuracao.cache_clear()
