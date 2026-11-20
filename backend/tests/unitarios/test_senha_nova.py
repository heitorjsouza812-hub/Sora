"""Senha nova (§8.2): envio de e-mail, configuração, rotas sem banco e o job do worker.

O caminho com PostgreSQL (token de uso único, sessões encerradas, trocar senha) está em
``tests/integracao/test_contas.py``.
"""

from __future__ import annotations

import smtplib
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, ClassVar

import fakeredis
import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.core import contas
from app.core.config import Configuracao, obter_configuracao
from app.core.dependencias import obter_redis
from app.emails import (
    EnviadorConsole,
    EnviadorMemoria,
    EnviadorResend,
    EnviadorSmtp,
    ErroEnvioEmail,
    MensagemEmail,
    criar_enviador,
    mensagem_redefinicao,
    remetente_valido,
)
from app.main import criar_aplicacao
from workers.emails import enviar_link_de_senha_nova

# ---------- mensagem e link ----------


def test_link_leva_o_token_no_fragmento() -> None:
    link = contas.link_de_senha_nova("https://app.sora.com.br/", "abc-123")
    assert link == "https://app.sora.com.br/redefinir-senha#token=abc-123"


def test_mensagem_tem_link_validade_e_escapa_o_nome() -> None:
    msg = mensagem_redefinicao("ana@x.com", "<b>Ana</b> Souza", "https://a/r#token=t&x", 30)
    assert msg.para == "ana@x.com"
    assert "https://a/r#token=t&x" in msg.texto
    assert "30 minutos" in msg.texto
    assert msg.html is not None
    assert "<b>Ana</b>" not in msg.html  # nome vem do usuário: sempre escapado
    assert "&lt;b&gt;Ana&lt;/b&gt;" in msg.html
    assert "token=t&amp;x" in msg.html


@pytest.mark.parametrize(
    ("remetente", "valido"),
    [
        ("nao-responda@sora.com.br", True),
        ("Sora <nao-responda@sora.com.br>", True),
        ("sora", False),
        ("sora@localhost", False),
        ("", False),
    ],
)
def test_remetente_valido(remetente: str, valido: bool) -> None:
    assert remetente_valido(remetente) is valido


# ---------- configuração ----------


def _config(**campos: Any) -> Configuracao:
    base: dict[str, Any] = {"ambiente": "teste"}
    return Configuracao(**{**base, **campos})


def test_email_desligado_por_padrao() -> None:
    config = _config()
    assert config.email_provedor == "nenhum"
    assert not config.email_ligado
    assert criar_enviador(config) is None


def test_console_so_fora_de_producao() -> None:
    assert isinstance(criar_enviador(_config(email_provedor="console")), EnviadorConsole)
    with pytest.raises(ValueError, match="console"):
        _config(ambiente="producao", email_provedor="console")


def test_smtp_exige_host_remetente_e_tls_em_producao() -> None:
    with pytest.raises(ValueError, match="EMAIL_REMETENTE"):
        _config(email_provedor="smtp", smtp_host="smtp.exemplo.com")
    with pytest.raises(ValueError, match="SMTP_HOST"):
        _config(email_provedor="smtp", email_remetente="Sora <a@sora.com.br>")
    with pytest.raises(ValueError, match="TLS"):
        _config(
            ambiente="producao",
            email_provedor="smtp",
            email_remetente="a@sora.com.br",
            smtp_host="smtp.exemplo.com",
            smtp_seguranca="nenhuma",
        )
    config = _config(
        email_provedor="smtp",
        email_remetente="Sora <a@sora.com.br>",
        smtp_host="smtp.exemplo.com",
        smtp_usuario="u",
        smtp_senha="segredo",
    )
    enviador = criar_enviador(config)
    assert isinstance(enviador, EnviadorSmtp)
    assert enviador.porta == 587
    assert "segredo" not in repr(enviador)


def test_resend_exige_chave() -> None:
    with pytest.raises(ValueError, match="RESEND_CHAVE"):
        _config(email_provedor="resend", email_remetente="a@sora.com.br")
    enviador = criar_enviador(
        _config(email_provedor="resend", email_remetente="a@sora.com.br", resend_chave="re_123")
    )
    assert isinstance(enviador, EnviadorResend)
    assert "re_123" not in repr(enviador)


# ---------- enviadores ----------

MENSAGEM = MensagemEmail(para="ana@x.com", assunto="Assunto", texto="Oi", html="<p>Oi</p>")


@respx.mock
async def test_resend_envia_e_nao_vaza_a_chave_no_erro() -> None:
    rota = respx.post("https://api.resend.com/emails").mock(
        return_value=httpx.Response(200, json={"id": "1"})
    )
    enviador = EnviadorResend(chave="re_segredo", remetente="a@sora.com.br")
    await enviador.enviar(MENSAGEM)
    pedido = rota.calls.last.request
    assert pedido.headers["Authorization"] == "Bearer re_segredo"
    assert b'"to":["ana@x.com"]' in pedido.content.replace(b" ", b"")

    rota.mock(return_value=httpx.Response(401, json={"message": "chave re_segredo inválida"}))
    with pytest.raises(ErroEnvioEmail) as erro:
        await enviador.enviar(MENSAGEM)
    assert "re_segredo" not in str(erro.value)
    assert "401" in str(erro.value)


class _SmtpFalso:
    instancias: ClassVar[list[_SmtpFalso]] = []
    falhar_login: ClassVar[bool] = False

    def __init__(self, host: str, porta: int, **_: Any) -> None:
        self.host, self.porta = host, porta
        self.tls = False
        self.login_feito: tuple[str, str] | None = None
        self.enviadas: list[Any] = []
        _SmtpFalso.instancias.append(self)

    def __enter__(self) -> _SmtpFalso:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def starttls(self, **_: Any) -> None:
        self.tls = True

    def login(self, usuario: str, senha: str) -> None:
        if _SmtpFalso.falhar_login:
            raise smtplib.SMTPAuthenticationError(535, f"usuario {usuario} senha {senha}".encode())
        self.login_feito = (usuario, senha)

    def send_message(self, mensagem: Any) -> None:
        self.enviadas.append(mensagem)


@pytest.fixture
def smtp_falso(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_SmtpFalso]]:
    _SmtpFalso.instancias = []
    _SmtpFalso.falhar_login = False
    monkeypatch.setattr("app.emails.smtplib.SMTP", _SmtpFalso)
    yield _SmtpFalso


async def test_smtp_usa_starttls_login_e_texto_mais_html(smtp_falso: type[_SmtpFalso]) -> None:
    enviador = EnviadorSmtp(
        host="smtp.x", porta=587, remetente="Sora <a@sora.com.br>", usuario="u", senha="s"
    )
    await enviador.enviar(MENSAGEM)
    conexao = smtp_falso.instancias[-1]
    assert conexao.tls
    assert conexao.login_feito == ("u", "s")
    email = conexao.enviadas[-1]
    assert email["To"] == "ana@x.com"
    assert email["From"] == "Sora <a@sora.com.br>"
    assert email.is_multipart()


async def test_smtp_erro_sem_usuario_nem_senha(smtp_falso: type[_SmtpFalso]) -> None:
    smtp_falso.falhar_login = True
    enviador = EnviadorSmtp(
        host="smtp.x", porta=587, remetente="a@sora.com.br", usuario="usuario-x", senha="senha-y"
    )
    with pytest.raises(ErroEnvioEmail) as erro:
        await enviador.enviar(MENSAGEM)
    assert "usuario-x" not in str(erro.value)
    assert "senha-y" not in str(erro.value)


# ---------- rotas sem banco ----------


@pytest.fixture
def redis_falso() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _cliente(redis: Any) -> TestClient:
    app = criar_aplicacao()
    app.dependency_overrides[obter_redis] = lambda: redis
    return TestClient(app)


def test_esqueci_senha_sem_email_ligado_responde_503(redis_falso: Any) -> None:
    with _cliente(redis_falso) as c:
        resposta = c.post("/v1/auth/esqueci-senha", json={"email": "ana@x.com"})
    assert resposta.status_code == 503
    assert "recuperação de senha" in resposta.json()["detail"]


def test_esqueci_senha_responde_202_enfileira_e_limita_por_email(
    redis_falso: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMAIL_PROVEDOR", "console")
    obter_configuracao.cache_clear()
    pedidos: list[tuple[str, dict[str, Any]]] = []

    async def enfileirar_falso(job: str, **args: Any) -> None:
        pedidos.append((job, args))

    monkeypatch.setattr("workers.fila.enfileirar", enfileirar_falso)
    with _cliente(redis_falso) as c:
        respostas = [
            c.post("/v1/auth/esqueci-senha", json={"email": " Ana@X.com "}).status_code
            for _ in range(4)
        ]
        invalido = c.post("/v1/auth/esqueci-senha", json={"email": "sem-arroba"})
    assert respostas == [202, 202, 202, 429]
    assert pedidos == [("enviar_link_de_senha_nova", {"email": "ana@x.com"})] * 3
    assert invalido.status_code == 422


def test_redefinir_senha_exige_senha_de_10_caracteres(redis_falso: Any) -> None:
    with _cliente(redis_falso) as c:
        resposta = c.post("/v1/auth/redefinir-senha", json={"token": "t", "senha_nova": "curta"})
    assert resposta.status_code == 422


def test_trocar_senha_exige_login(redis_falso: Any) -> None:
    with _cliente(redis_falso) as c:
        resposta = c.post("/v1/conta/senha", json={"senha_atual": "x" * 10, "senha_nova": "y" * 10})
    assert resposta.status_code == 401


# ---------- job do worker ----------


def _ctx(enviador: Any) -> dict[str, Any]:
    @asynccontextmanager
    async def sessoes() -> AsyncIterator[Any]:
        async def commit() -> None:
            return None

        yield SimpleNamespace(commit=commit)

    return {"email": enviador, "sessoes": sessoes}


async def test_job_sem_email_ligado_nao_faz_nada() -> None:
    assert await enviar_link_de_senha_nova({"email": None}, "ana@x.com") is False


async def test_job_sem_conta_nao_envia(monkeypatch: pytest.MonkeyPatch) -> None:
    async def sem_conta(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(contas, "criar_link_de_senha_nova", sem_conta)
    enviador = EnviadorMemoria()
    assert await enviar_link_de_senha_nova(_ctx(enviador), "ninguem@x.com") is False
    assert enviador.enviadas == []


async def test_job_envia_o_link_para_o_email_da_conta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_URL", "https://app.sora.com.br")
    obter_configuracao.cache_clear()
    usuario = SimpleNamespace(email="ana@x.com", nome="Ana Souza")

    async def com_conta(*_: Any, **__: Any) -> tuple[Any, str]:
        return usuario, "token-secreto"

    monkeypatch.setattr(contas, "criar_link_de_senha_nova", com_conta)
    enviador = EnviadorMemoria()
    assert await enviar_link_de_senha_nova(_ctx(enviador), "ana@x.com") is True
    [msg] = enviador.enviadas
    assert msg.para == "ana@x.com"
    assert "https://app.sora.com.br/redefinir-senha#token=token-secreto" in msg.texto
    assert msg.texto.startswith("Olá, Ana.")


async def test_job_falha_no_envio_sobe_para_o_arq_tentar_de_novo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def com_conta(*_: Any, **__: Any) -> tuple[Any, str]:
        return SimpleNamespace(email="ana@x.com", nome="Ana"), "t"

    monkeypatch.setattr(contas, "criar_link_de_senha_nova", com_conta)
    with pytest.raises(ErroEnvioEmail):
        await enviar_link_de_senha_nova(_ctx(EnviadorMemoria(falhar=True)), "ana@x.com")
