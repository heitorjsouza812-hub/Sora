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
    # passou dos 30 s: não devolve mais o mesmo par, mas ainda pode reemitir (resposta perdida)
    assert contas.classificar_token(fora, "antigo", AGORA) == "reemitir"


def test_anterior_depois_da_janela_reemite_ate_5_minutos() -> None:
    """Decisão 6: F5 seguidos com a resposta perdida não derrubam mais o login."""
    dentro = _sessao(anterior_rotacionado_em=AGORA - contas.JANELA_REEMISSAO)
    fora = _sessao(
        anterior_rotacionado_em=AGORA - contas.JANELA_REEMISSAO - timedelta(microseconds=1)
    )
    assert contas.classificar_token(dentro, "antigo", AGORA) == "reemitir"
    assert contas.classificar_token(fora, "antigo", AGORA) == "reutilizado"


def test_reemissao_tem_teto() -> None:
    perto = AGORA - timedelta(minutes=1)
    no_teto = _sessao(anterior_rotacionado_em=perto, reemissoes=contas.MAX_REEMISSOES)
    abaixo = _sessao(anterior_rotacionado_em=perto, reemissoes=contas.MAX_REEMISSOES - 1)
    assert contas.classificar_token(abaixo, "antigo", AGORA) == "reemitir"
    assert contas.classificar_token(no_teto, "antigo", AGORA) == "reutilizado"


def test_token_abandonado_na_reemissao_e_reuso() -> None:
    """O atual que a reemissão abandonou vai para o histórico: se aparecer, havia duas cópias."""
    sessao = _sessao(
        token_hash="novo",
        anterior_rotacionado_em=AGORA,
        historico_hashes=["abandonado"],
        reemissoes=1,
    )
    assert contas.classificar_token(sessao, "abandonado", AGORA) == "reutilizado"


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

    async def renovar(_sessao: object, token: str | None, *_: object) -> tuple[str, str, str]:
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


async def test_historico_de_hashes_tem_teto_e_mantem_as_geracoes_mais_novas(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    token, token_hash = seguranca.gerar_token_renovacao()
    antigos = [f"g{i}" for i in range(contas.MAX_HISTORICO_HASHES)]
    registro = _sessao(
        id=uuid4(),
        token_hash=token_hash,
        historico_hashes=antigos,
        expira_em=datetime.now(UTC) + timedelta(days=30),
    )
    monkeypatch.setattr(contas, "_sessao_do_token", AsyncMock(return_value=registro))
    await contas.renovar(AsyncMock(), token)
    assert len(registro.historico_hashes) == contas.MAX_HISTORICO_HASHES
    assert registro.historico_hashes[-1] == token_hash
    assert "g0" not in registro.historico_hashes and "g1" in registro.historico_hashes


async def test_renovar_fora_da_janela_nao_devolve_o_par_e_o_apaga(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    token, token_hash = seguranca.gerar_token_renovacao()
    agora = datetime.now(UTC)
    registro = _sessao(
        id=uuid4(),
        token_hash="outro-atual",
        anterior_hash=token_hash,
        anterior_rotacionado_em=agora - contas.JANELA_REEMISSAO - timedelta(seconds=1),
        historico_hashes=[],
        par_atual_cifrado=b"segredo",
        expira_em=agora + timedelta(days=30),
    )
    banco = AsyncMock()
    monkeypatch.setattr(contas, "_sessao_do_token", AsyncMock(return_value=registro))
    with pytest.raises(contas.ErroCredenciais):
        await contas.renovar(banco, token)
    assert registro.par_atual_cifrado is None and registro.encerrada_em is not None


async def test_reemissao_gera_par_novo_e_abandona_o_atual(monkeypatch) -> None:
    """Entre 30 s e 5 min: par novo (não o guardado), o atual nunca usado vai para o histórico e
    o anterior continua o mesmo; o token de acesso leva o id da sessão (``sid``)."""
    from unittest.mock import AsyncMock

    token, token_hash = seguranca.gerar_token_renovacao()
    agora = datetime.now(UTC)
    registro = _sessao(
        id=uuid4(),
        token_hash="atual-nunca-usado",
        anterior_hash=token_hash,
        anterior_rotacionado_em=agora - timedelta(minutes=1),
        historico_hashes=[],
        par_atual_cifrado=b"segredo",
        expira_em=agora + timedelta(days=30),
        reemissoes=0,
    )
    monkeypatch.setattr(contas, "_sessao_do_token", AsyncMock(return_value=registro))
    novo, acesso, _cliente = await contas.renovar(AsyncMock(), token)
    assert seguranca.hash_token(novo) == registro.token_hash
    assert registro.anterior_hash == token_hash
    assert registro.historico_hashes == ["atual-nunca-usado"]
    assert registro.reemissoes == 1
    assert registro.encerrada_em is None
    assert registro.par_atual_cifrado not in (None, b"segredo")
    assert seguranca.decodificar_token_acesso(acesso)["sid"] == str(registro.id)


async def test_sair_apaga_o_par_cifrado(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    registro = _sessao(id=uuid4(), par_atual_cifrado=b"segredo")
    monkeypatch.setattr(contas, "_sessao_do_token", AsyncMock(return_value=registro))
    await contas.sair(AsyncMock(), "qualquer")
    assert registro.par_atual_cifrado is None and registro.encerrada_em is not None


def test_par_vencido_so_depois_da_janela() -> None:
    dentro = _sessao(anterior_rotacionado_em=AGORA - contas.JANELA_TOLERANCIA_RENOVACAO)
    fora = _sessao(
        anterior_rotacionado_em=AGORA - contas.JANELA_TOLERANCIA_RENOVACAO - timedelta(seconds=1)
    )
    assert not contas.par_vencido(dentro, AGORA)
    assert contas.par_vencido(fora, AGORA)
    assert contas.par_vencido(_sessao(anterior_rotacionado_em=None), AGORA)


async def test_token_de_sessao_encerrada_ou_conta_apagada_e_recusado() -> None:
    """Sair (ou reuso detectado, ou apagar a conta) derruba na hora o token de acesso: antes ele
    continuava valendo os 15 min que faltavam."""
    from fakeredis import FakeAsyncRedis
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from starlette.requests import Request

    from app.core.dependencias import usuario_atual

    redis = FakeAsyncRedis(decode_responses=True)
    app = FastAPI()
    app.state.redis = redis
    usuario, sessao_id = uuid4(), uuid4()
    token = seguranca.criar_token_acesso({"sub": str(usuario), "sid": str(sessao_id)})
    credenciais = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    def requisicao() -> Request:
        return Request({"type": "http", "headers": [], "state": {}, "app": app})

    assert await usuario_atual(requisicao(), credenciais) == usuario
    await contas.revogar_acessos(redis, sessao_id=sessao_id)
    with pytest.raises(HTTPException) as erro:
        await usuario_atual(requisicao(), credenciais)
    assert erro.value.status_code == 401

    outro = seguranca.criar_token_acesso({"sub": str(usuario), "sid": str(uuid4())})
    outras = HTTPAuthorizationCredentials(scheme="Bearer", credentials=outro)
    assert await usuario_atual(requisicao(), outras) == usuario  # outra sessão segue valendo
    await contas.revogar_acessos(redis, usuario_id=usuario)  # conta apagada: todas caem
    with pytest.raises(HTTPException):
        await usuario_atual(requisicao(), outras)
