"""Validação adversarial (Tranca) da chamada SÍNCRONA do LiteLLM protegido: rebinding e redirect."""

import http.server
import threading
from typing import Any

import pytest

from app.llm import provedores as p


class _Servidor:
    def __init__(self, resposta: Any) -> None:
        self.acessos: list[str] = []
        dono = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("content-length", 0)))
                dono.acessos.append(self.path)
                resposta(self)

            def log_message(self, *args: Any) -> None:
                pass

        self.http = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.porta = self.http.server_port
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def fechar(self) -> None:
        self.http.shutdown()


def _ok(h: http.server.BaseHTTPRequestHandler) -> None:
    h.send_response(200)
    h.end_headers()
    h.wfile.write(b"{}")


def _chamar(cliente: p.ClienteLiteLLMProtegido, porta: int, modelo: str = "openai/x") -> None:
    try:
        cliente.completion(
            model=modelo,
            api_base=f"http://pub.test:{porta}",
            api_key="k",
            messages=[{"role": "user", "content": "oi"}],
            num_retries=0,
            timeout=5,
        )
    except Exception:
        pass


@pytest.mark.parametrize("modelo", ["openai/x", "ollama/x"])
def test_sincrono_dns_rebinding_e_barrado_na_conexao(modelo: str) -> None:
    interno = _Servidor(_ok)
    chamadas: list[int] = []

    def resolver(host: str, porta: int) -> list[str]:
        chamadas.append(1)
        return (
            ["93.184.216.34"] if len(chamadas) == 1 else ["127.0.0.1"]
        )  # troca depois da checagem

    try:
        _chamar(p.ClienteLiteLLMProtegido(resolver_sinc=resolver), interno.porta, modelo)
    finally:
        interno.fechar()
    assert len(chamadas) >= 2, "a conexão precisa resolver e conferir de novo"
    assert interno.acessos == []


@pytest.mark.parametrize("mutante", [False, True], ids=["codigo_real", "mutante_segue_redirect"])
def test_sincrono_nao_segue_redirect_para_destino_interno(
    monkeypatch: pytest.MonkeyPatch, mutante: bool
) -> None:
    interno = _Servidor(_ok)

    def redireciona(h: http.server.BaseHTTPRequestHandler) -> None:
        h.send_response(307)
        h.send_header("location", f"http://pub.test:{interno.porta}/interno")
        h.end_headers()

    publico = _Servidor(redireciona)
    # libera loopback na camada de IP: só a política de redirecionamento fica decidindo
    monkeypatch.setattr(p, "ip_bloqueado", lambda ip: False)
    if mutante:
        import httpx

        real = p.transporte_seguro_sincrono
        from openai import OpenAI

        def cliente_mutante(self: Any, prefixo: str, kwargs: dict[str, Any]) -> Any:
            http_ = httpx.Client(
                transport=real(self._resolver_sinc), follow_redirects=True, trust_env=False
            )
            return OpenAI(
                api_key="k", base_url=kwargs["api_base"], http_client=http_, max_retries=0
            )

        monkeypatch.setattr(p.ClienteLiteLLMProtegido, "_cliente_sincrono", cliente_mutante)
    try:
        _chamar(
            p.ClienteLiteLLMProtegido(resolver_sinc=lambda h, port: ["127.0.0.1"]), publico.porta
        )
    finally:
        publico.fechar()
        interno.fechar()
    assert publico.acessos, "controle: o primeiro servidor precisa ser alcançado"
    assert (interno.acessos != []) if mutante else (interno.acessos == [])


def test_sincrono_prefixos_sem_suporte_com_api_base_sao_recusados() -> None:
    for modelo in ("anthropic/x", "gemini/x", "groq/x", "openrouter/x"):
        with pytest.raises(p.DestinoBloqueado):
            p.ClienteLiteLLMProtegido().completion(
                model=modelo, api_base="https://93.184.216.34", messages=[]
            )
