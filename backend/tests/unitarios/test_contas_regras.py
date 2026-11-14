"""Regras de sessão e das rotas de conta, sem banco; especificação §8.2."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import contas, seguranca
from app.core.banco import obter_sessao
from app.core.dependencias import obter_redis
from app.main import criar_aplicacao
from app.modelos.tabelas import Sessao

AGORA = datetime(2026, 10, 14, tzinfo=UTC)


def _sessao(**campos: object) -> Sessao:
    base: dict[str, object] = {
        "usuario_id": uuid4(),
        "token_hash": "atual",
        "anterior_hash": "antigo",
        "anterior_rotacionado_em": AGORA - timedelta(days=1),
        "expira_em": AGORA + timedelta(days=1),
        "encerrada_em": None,
    }
    return Sessao(**{**base, **campos})


def test_token_atual_e_valido() -> None:
    assert contas.classificar_token(_sessao(), "atual", AGORA) == "valido"


def test_token_anterior_e_reuso() -> None:
    assert contas.classificar_token(_sessao(), "antigo", AGORA) == "reutilizado"


def test_token_anterior_dentro_da_janela_e_tolerado() -> None:
    sessao = _sessao(anterior_rotacionado_em=AGORA - timedelta(seconds=10))
    assert contas.classificar_token(sessao, "antigo", AGORA) == "tolerado"


def test_tolerancia_inclui_30_segundos_mas_nao_um_instante_a_mais() -> None:
    no_limite = _sessao(anterior_rotacionado_em=AGORA - contas.JANELA_TOLERANCIA_RENOVACAO)
    fora = _sessao(
        anterior_rotacionado_em=no_limite.anterior_rotacionado_em - timedelta(microseconds=1)
    )
    assert contas.classificar_token(no_limite, "antigo", AGORA) == "tolerado"
    assert contas.classificar_token(fora, "antigo", AGORA) == "reutilizado"


@pytest.mark.parametrize(
    "sessao",
    [None, _sessao(encerrada_em=AGORA), _sessao(expira_em=AGORA - timedelta(seconds=1))],
)
def test_sessao_ausente_encerrada_ou_expirada_e_invalida(sessao: Sessao | None) -> None:
    assert contas.classificar_token(sessao, "atual", AGORA) == "invalido"


def test_token_desconhecido_e_invalido() -> None:
    assert contas.classificar_token(_sessao(), "outro", AGORA) == "invalido"


def test_cliente_desktop_so_com_o_cabecalho_exato() -> None:
    assert contas.cliente_da_requisicao("desktop") == "desktop"
    assert contas.cliente_da_requisicao(" Desktop ") == "desktop"
    assert contas.cliente_da_requisicao(None) == "web"
    assert contas.cliente_da_requisicao("mobile") == "web"


def test_email_e_normalizado() -> None:
    assert contas.normalizar_email("  Ana@Exemplo.COM ") == "ana@exemplo.com"


@pytest.fixture
def aplicacao_sem_infra() -> FastAPI:
    app = criar_aplicacao()
    app.dependency_overrides[obter_sessao] = lambda: None
    app.dependency_overrides[obter_redis] = lambda: None
    return app


async def _entrar_ok(*_a: object, **_k: object) -> tuple[str, str]:
    return "renovacao-123", "acesso-abc"


def test_entrar_no_navegador_poe_a_renovacao_no_cookie_httponly(
    aplicacao_sem_infra: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(contas, "entrar", _entrar_ok)
    with TestClient(aplicacao_sem_infra) as c:
        r = c.post("/v1/auth/entrar", json={"email": "a@b.com", "senha": "x"})
    assert r.json() == {"token_acesso": "acesso-abc", "token_renovacao": None}
    cookie = r.headers["set-cookie"]
    assert "sora_renovacao=renovacao-123" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/v1/auth" in cookie


def test_entrar_no_desktop_devolve_a_renovacao_no_corpo_sem_cookie(
    aplicacao_sem_infra: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(contas, "entrar", _entrar_ok)
    with TestClient(aplicacao_sem_infra) as c:
        r = c.post(
            "/v1/auth/entrar",
            json={"email": "a@b.com", "senha": "x"},
            headers={"X-Sora-Cliente": "desktop"},
        )
    assert r.json() == {"token_acesso": "acesso-abc", "token_renovacao": "renovacao-123"}
    assert "set-cookie" not in r.headers


def test_limite_vira_429_com_retry_after(
    aplicacao_sem_infra: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def limitado(*_a: object, **_k: object) -> tuple[str, str]:
        raise contas.ErroLimite(321)

    monkeypatch.setattr(contas, "entrar", limitado)
    with TestClient(aplicacao_sem_infra) as c:
        r = c.post("/v1/auth/entrar", json={"email": "a@b.com", "senha": "x"})
    assert r.status_code == 429
    assert r.headers["retry-after"] == "321"


def test_renovar_aceita_cookie_ou_corpo(
    aplicacao_sem_infra: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    recebidos: list[str | None] = []

    async def renovar(_sessao: object, token: str | None) -> tuple[str, str, str]:
        recebidos.append(token)
        return "novo", "acesso", "desktop" if token == "do-corpo" else "web"

    monkeypatch.setattr(contas, "renovar", renovar)
    with TestClient(aplicacao_sem_infra) as c:
        r1 = c.post("/v1/auth/renovar", json={"token_renovacao": "do-corpo"})
        c.cookies.set("sora_renovacao", "do-cookie", path="/v1/auth")
        r2 = c.post("/v1/auth/renovar")
    assert recebidos == ["do-corpo", "do-cookie"]
    assert r1.json()["token_renovacao"] == "novo"
    assert r2.json()["token_renovacao"] is None


def test_rotas_protegidas_exigem_bearer_valido(aplicacao_sem_infra: FastAPI) -> None:
    with TestClient(aplicacao_sem_infra) as c:
        sem_token = c.get("/v1/eu")
        assert sem_token.status_code == 401
        assert sem_token.json() == {"detail": "Entre na sua conta para continuar."}
        ruim = c.get("/v1/eu", headers={"Authorization": "Bearer lixo"})
        assert ruim.status_code == 401
        expirado = seguranca.criar_token_acesso({"sub": str(uuid4())}, timedelta(seconds=-1))
        resposta = c.get("/v1/eu", headers={"Authorization": f"Bearer {expirado}"})
        assert resposta.status_code == 401


def test_token_de_duas_geracoes_atras_e_reuso_mesmo_dentro_da_janela() -> None:
    sessao = _sessao(anterior_rotacionado_em=AGORA, historico_hashes=["mais-antigo"])
    assert contas.classificar_token(sessao, "mais-antigo", AGORA) == "reutilizado"


def test_validade_estendida_nao_prolonga_janela_original() -> None:
    sessao = _sessao(expira_em=AGORA + timedelta(days=90))
    assert contas.classificar_token(sessao, "antigo", AGORA) == "reutilizado"


async def test_tres_recuperacoes_devolvem_par_atual_sem_estender_rotacao(monkeypatch) -> None:
    from datetime import datetime
    from unittest.mock import AsyncMock

    token, token_hash = seguranca.gerar_token_renovacao()
    registro = _sessao(
        id=uuid4(),
        token_hash=token_hash,
        historico_hashes=[],
        expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    banco = AsyncMock()
    consulta = AsyncMock(return_value=registro)
    monkeypatch.setattr(contas, "_sessao_do_token", consulta)
    primeiro = await contas.renovar(banco, token)
    rotacao = registro.anterior_rotacionado_em
    for _ in range(3):
        assert await contas.renovar(banco, token) == primeiro
        assert registro.anterior_rotacionado_em == rotacao
        assert registro.anterior_hash == token_hash
    assert registro.par_atual_cifrado and primeiro[0].encode() not in registro.par_atual_cifrado
    assert registro.historico_hashes == [token_hash]


async def test_reuso_antigo_encerra_e_persiste_familia(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    registro = _sessao(historico_hashes=[seguranca.hash_token("duas-geracoes")])
    registro.expira_em = datetime.now(UTC) + timedelta(days=1)
    banco = AsyncMock()
    monkeypatch.setattr(contas, "_sessao_do_token", AsyncMock(return_value=registro))
    with pytest.raises(contas.ErroCredenciais):
        await contas.renovar(banco, "duas-geracoes")
    assert registro.encerrada_em is not None
    banco.commit.assert_awaited_once()
