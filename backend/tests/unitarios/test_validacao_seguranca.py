"""Validação adversarial (Tranca): autorização entre usuários, trava do modelo falso, config.

Os testes marcados ``xfail(strict=True)`` provam um achado ABERTO da nota "Segurança — Achados":
quando a correção entrar, o teste passa, o ``strict`` acusa XPASS e a marca é removida.
"""

import re
from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID, uuid4

import fakeredis
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.banco import obter_sessao
from app.core.config import Configuracao, obter_configuracao
from app.core.dependencias import obter_redis
from app.core.seguranca import criar_token_acesso
from app.eventos.streams import canal_usuario, publicar_evento
from app.eventos.tipos import EtapaAtualizada
from app.main import criar_aplicacao

RAIZ = Path(__file__).resolve().parents[2]
ANA, BRUNO = uuid4(), uuid4()
CONVERSA_DA_ANA = uuid4()


class BancoFalso:
    """Sessão que de fato avalia os parâmetros do ``select`` (não devolve resposta fixa)."""

    dono_das_conversas: ClassVar[dict[UUID, UUID]] = {CONVERSA_DA_ANA: ANA}

    async def execute(self, consulta: Any) -> "BancoFalso":
        params = {v for v in consulta.compile().params.values() if isinstance(v, UUID)}
        conversa = next((p for p in params if p in self.dono_das_conversas), None)
        donos = {p for p in params if p in (ANA, BRUNO)}
        self._achou = conversa is not None and self.dono_das_conversas[conversa] in donos
        return self

    def scalar_one_or_none(self) -> UUID | None:
        return CONVERSA_DA_ANA if self._achou else None


def _estado(modelo: str) -> EtapaAtualizada:
    return EtapaAtualizada(
        etapa_id=uuid4(), status="executando", progresso=1, modelo=modelo, tokens=1, custo_usd=0
    )


def _auth(usuario: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {criar_token_acesso({'sub': str(usuario)})}"}


@pytest.fixture
def api():
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    app = criar_aplicacao()
    app.dependency_overrides[obter_sessao] = lambda: BancoFalso()
    app.dependency_overrides[obter_redis] = lambda: redis
    return TestClient(app), redis


# ------------------------------------------------------------ autorização entre usuários


def test_bruno_nao_abre_eventos_da_conversa_da_ana(api) -> None:
    cliente, _ = api
    r = cliente.get(f"/v1/conversas/{CONVERSA_DA_ANA}/eventos", headers=_auth(BRUNO))
    assert r.status_code == 404


def test_sem_token_ou_token_forjado_nao_passa(api) -> None:
    cliente, _ = api
    url = f"/v1/conversas/{CONVERSA_DA_ANA}/eventos"
    assert cliente.get(url).status_code in (401, 403)
    assert cliente.get(url, headers={"Authorization": "Bearer lixo"}).status_code == 401
    # alg=none e assinatura com outro segredo
    import jwt

    for token in (
        jwt.encode({"sub": str(ANA)}, key=None, algorithm="none"),
        jwt.encode(
            {"sub": str(ANA), "exp": 4102444800}, "outro-segredo-32-bytes-aaaaaaaa", "HS256"
        ),
    ):
        r = cliente.get(url, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


async def test_stream_do_usuario_so_entrega_eventos_dele(api) -> None:
    from app.eventos.sse import gerar_sse

    _, redis = api
    await publicar_evento(redis, _estado("ana"), CONVERSA_DA_ANA, ANA)
    await publicar_evento(redis, _estado("bruno"), uuid4(), BRUNO)
    lidos = []
    async for msg in gerar_sse(redis, canal_usuario(BRUNO), "0-0", bloquear_ms=50):
        lidos.append(msg)
        if len(lidos) == 1:
            break
    assert '"modelo":"bruno"' in lidos[0]["data"]
    assert all('"modelo":"ana"' not in m["data"] for m in lidos)


def test_rotas_de_dados_exigem_login(api) -> None:
    """Toda rota de /v1 fora de /auth e /health devolve 401/403 sem token (nada vaza)."""
    cliente, _ = api
    abertas = {"/v1/auth/cadastrar", "/v1/auth/entrar", "/v1/auth/renovar", "/v1/auth/sair"}
    for rota in cliente.app.routes:
        caminho = getattr(rota, "path", "")
        if not caminho.startswith("/v1") or caminho in abertas:
            continue
        url = re.sub(r"\{[^}]+\}", str(uuid4()), caminho)
        for metodo in rota.methods - {"HEAD", "OPTIONS"}:
            r = cliente.request(metodo, url)
            assert r.status_code in (401, 403), f"{metodo} {caminho} -> {r.status_code}"


# ------------------------------------------------------------------- trava do modelo falso


def test_fabrica_nao_devolve_modelo_falso_em_producao(monkeypatch: pytest.MonkeyPatch) -> None:
    """VAL-02: o worker é quem chama modelos; a fábrica também olha o AMBIENTE."""
    from app.llm.falso import ModeloFalsoEmProducao, modelo_falso_ativo

    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    obter_configuracao.cache_clear()
    try:
        with pytest.raises(ModeloFalsoEmProducao):  # recusa em voz alta, não devolve modelo real
            modelo_falso_ativo()
    finally:
        obter_configuracao.cache_clear()


def test_worker_chama_a_trava_do_modelo_falso() -> None:
    codigo = (RAIZ / "workers" / "configuracao.py").read_text(encoding="utf-8")
    assert "verificar_modelo_falso_permitido" in codigo


# ---------------------------------------------------------------- config insegura por padrão


def test_ambiente_sem_variavel_nao_vira_desenvolvimento(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AMBIENTE", raising=False)
    c = Configuracao(_env_file=None)  # type: ignore[call-arg]
    assert c.ambiente != "desenvolvimento"


def test_producao_recusa_jwt_segredo_fraco(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "producao")
    monkeypatch.setenv("JWT_SEGREDO", "x")
    with pytest.raises(ValidationError):
        Configuracao(_env_file=None)  # type: ignore[call-arg]


def test_chave_mestra_invalida_quebra_na_configuracao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAVE_MESTRA", "curta")
    with pytest.raises(ValidationError):
        Configuracao(_env_file=None)  # type: ignore[call-arg]


# ------------------------------------------------------------------ entradas sem limite


def test_login_recusa_senha_gigante() -> None:
    from app.modelos.esquemas import ApagarContaEntrada, CadastroEntrada, LoginEntrada

    gigante = "a" * 5_000_000
    with pytest.raises(ValidationError):
        LoginEntrada(email="a@b.com", senha=gigante)
    with pytest.raises(ValidationError):
        ApagarContaEntrada(senha=gigante)
    with pytest.raises(ValidationError):
        CadastroEntrada(nome="a", email="a@b.com", senha=gigante)


def test_cadastro_recusa_email_invalido() -> None:
    from app.modelos.esquemas import CadastroEntrada

    with pytest.raises(ValidationError):
        CadastroEntrada(nome="a", email="isto não é e-mail", senha="uma-senha-bem-longa")


# ------------------------------------------------- redirecionamento na chamada do LiteLLM


@pytest.mark.parametrize("mutante", [False, True], ids=["codigo_real", "mutante_segue_redirect"])
async def test_chamada_do_litellm_nao_segue_redirect_para_destino_interno(
    monkeypatch: pytest.MonkeyPatch, mutante: bool
) -> None:
    """Libera a conexão para loopback (a checagem de IP não pode ser o que segura o teste): só a
    política de redirecionamento decide. O mutante prova que o teste enxerga a falha."""
    import http.server
    import threading

    from app.llm import provedores as p

    acessos: list[str] = []

    class Interno(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("content-length", 0)))
            acessos.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args: Any) -> None:
            pass

    interno = http.server.HTTPServer(("127.0.0.1", 0), Interno)

    class Publico(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("content-length", 0)))
            self.send_response(307)
            self.send_header("location", f"http://127.0.0.1:{interno.server_port}/interno")
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            pass

    publico = http.server.HTTPServer(("127.0.0.1", 0), Publico)
    for servidor in (interno, publico):
        threading.Thread(target=servidor.serve_forever, daemon=True).start()

    async def so_o_publico(host: str, porta: int, resolver: Any = None) -> list[str]:
        if porta != publico.server_port:
            raise p.EnderecoBloqueado("interno")
        return ["93.184.216.34"]  # a 1ª checagem enxerga um IP público

    async def liberado(host: str, porta: int, resolver: Any = None) -> list[str]:
        return ["127.0.0.1"]

    from app.busca import ler_pagina as lp

    monkeypatch.setattr(p, "ips_permitidos", so_o_publico)
    monkeypatch.setattr(lp, "ips_permitidos", liberado)
    if mutante:
        import httpx

        monkeypatch.setattr(
            p,
            "cliente_http_seguro",
            lambda resolver=None: httpx.AsyncClient(
                transport=lp.transporte_seguro(), follow_redirects=True, trust_env=False
            ),
        )
    try:
        await p.ClienteLiteLLMProtegido().acompletion(
            model="openai/x",
            api_base=f"http://127.0.0.1:{publico.server_port}",
            api_key="k",
            messages=[{"role": "user", "content": "oi"}],
            num_retries=0,
        )
    except Exception:
        pass
    finally:
        interno.shutdown()
        publico.shutdown()
    assert (acessos != []) if mutante else (acessos == [])
