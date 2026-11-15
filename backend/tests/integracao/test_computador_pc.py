# ruff: noqa: F811
"""C3 (Vela-3): canal do app de desktop com Postgres, Redis e a API reais.

O app de desktop é simulado por um cliente HTTP com ``X-Sora-Cliente: desktop`` que faz o
long-poll de ``/v1/computador-pc/comandos`` e responde por POST, como a ponte Rust. O worker é o
``ProvedorPcUsuario`` de verdade, com os cartões no banco (sistema de aprovações).
"""

from __future__ import annotations

import asyncio
import base64
import io
import time
from typing import Any
from uuid import UUID

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select

from app.computador.interface import AcaoComputador, AcaoResolvida
from app.computador.pc_usuario import PARADO, ProvedorPcUsuario
from app.computador.pc_usuario_cartoes import FERRAMENTA_PROGRAMA
from app.ferramentas.base import ErroFerramenta
from app.modelos.tabelas import RegraPermissao
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import SENHA, entrar

pytestmark = pytest.mark.integracao

DESKTOP = {"X-Sora-Cliente": "desktop"}


async def entrar_desktop(cliente: httpx.AsyncClient, email: str) -> tuple[dict, str]:
    """Login do app de desktop: token de acesso + token de renovação (o do cofre do Windows)."""
    resposta = await cliente.post(
        "/v1/auth/entrar", json={"email": email, "senha": SENHA}, headers=DESKTOP
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["token_renovacao"]
    return {"Authorization": f"Bearer {corpo['token_acesso']}", **DESKTOP}, corpo["token_renovacao"]


def _png() -> str:
    from PIL import Image

    saida = io.BytesIO()
    Image.new("RGB", (32, 20), (5, 6, 8)).save(saida, format="PNG")
    return base64.b64encode(saida.getvalue()).decode()


@pytest.fixture(autouse=True)
def _fila_limpa():
    from workers.fila import configurar_fila

    configurar_fila(None)
    yield
    configurar_fila(None)


class AppDesktop:
    """Simula a ponte do app: long-poll, executa (aqui: respostas prontas) e responde."""

    def __init__(self, cliente: httpx.AsyncClient, cabecalhos: dict, sessao_id: str) -> None:
        self.cliente, self.cabecalhos, self.sessao_id = cliente, cabecalhos, sessao_id
        self.recebidos: list[dict[str, Any]] = []
        self.permitidos_vistos: list[list[str]] = []
        self.respostas_post: list[int] = []

    def responder(self, comando: dict[str, Any]) -> dict[str, Any]:
        if comando["operacao"] == "observar":
            return {
                "ok": True,
                "resultado": {
                    "png": _png(),
                    "largura": 32,
                    "altura": 20,
                    "janelas": [
                        {
                            "id": "77",
                            "titulo": "Sem título - Bloco de Notas",
                            "ativa": True,
                            "largura": 32,
                            "altura": 20,
                            "programa": "Notepad.exe",
                        }
                    ],
                    "arvore": [{"ref": "e1", "papel": "documento", "nome": "Editor de texto"}],
                },
            }
        if comando["operacao"] == "agir":
            permitidos = comando["dados"]["programas_permitidos"]
            self.permitidos_vistos.append(permitidos)
            if "notepad.exe" not in permitidos:
                return {
                    "ok": False,
                    "erro": {
                        "codigo": "programa_nao_permitido",
                        "programa": "Notepad.exe",
                        "titulo": "Sem título - Bloco de Notas",
                    },
                }
        return {"ok": True, "resultado": {}}

    async def rodar(self) -> None:
        while True:
            resposta = await self.cliente.get(
                "/v1/computador-pc/comandos",
                params={"sessao_id": self.sessao_id, "espera": 2},
                headers=self.cabecalhos,
            )
            if resposta.status_code == 204:
                continue
            assert resposta.status_code == 200, resposta.text
            comando = resposta.json()
            # a ponte Rust recusa como "vencido" um comando sem prazo absoluto (Vela-6)
            assert comando["prazo_em_ms"] > time.time() * 1000, comando
            self.recebidos.append(comando)
            corpo = {"sessao_id": self.sessao_id, **self.responder(comando)}
            post = await self.cliente.post(
                f"/v1/computador-pc/comandos/{comando['id']}/resultado",
                json=corpo,
                headers=self.cabecalhos,
            )
            self.respostas_post.append(post.status_code)


async def test_canal_do_app_de_desktop_de_ponta_a_ponta(mundo: Mundo) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        a = await entrar(cliente, mundo.fabrica, "vela3-a@exemplo.com")
        b = await entrar(cliente, mundo.fabrica, "vela3-b@exemplo.com")
        bot = (
            await cliente.post("/v1/agentes", json={"descricao": "Organiza notas"}, headers=a)
        ).json()
        bot_b = (
            await cliente.post("/v1/agentes", json={"descricao": "Outro bot"}, headers=b)
        ).json()
        da, renovacao = await entrar_desktop(cliente, "vela3-a@exemplo.com")

        # só o app de desktop abre sessão; sem login, 401
        corpo = {
            "dispositivo": "PC da Ana",
            "autorizados": [bot["id"], bot_b["id"]],
            "token_renovacao": renovacao,
        }
        assert (
            await cliente.post("/v1/computador-pc/sessao", json=corpo, headers=a)
        ).status_code == 403
        assert (
            await cliente.post("/v1/computador-pc/sessao", json=corpo, headers=DESKTOP)
        ).status_code == 401
        assert (await cliente.get("/v1/computador-pc/estado", headers=a)).json()[
            "conectado"
        ] is False

        # o cabeçalho não basta: sem a prova do cofre do desktop, 403 (Cerca B3)
        sem_prova = {k: v for k, v in corpo.items() if k != "token_renovacao"}
        assert (
            await cliente.post("/v1/computador-pc/sessao", json=sem_prova, headers={**a, **DESKTOP})
        ).status_code == 403
        sessao = await cliente.post("/v1/computador-pc/sessao", json=corpo, headers=da)
        assert sessao.status_code == 200, sessao.text
        dados = sessao.json()
        assert dados["autorizados"] == [bot["id"]]  # bot de outra conta some da lista
        sessao_id = dados["sessao_id"]
        estado = (await cliente.get("/v1/computador-pc/estado", headers=a)).json()
        assert estado["conectado"] is True and estado["dispositivo"] == "PC da Ana"

        redis = Redis.from_url(mundo.url_redis, decode_responses=True)
        provedor = ProvedorPcUsuario(redis=redis, espera_cartao_s=20)
        usuario_id = UUID(dados["usuario_id"])
        app = AppDesktop(cliente, da, sessao_id)
        tarefa = asyncio.create_task(app.rodar())
        try:
            computador = await provedor.obter(usuario_id, UUID(bot["id"]))
            computador.intervalo_cartao_s = 0.2
            observacao = await computador.observar()
            assert observacao.janelas[0].programa == "notepad.exe"
            assert observacao.arvore == [
                {"ref": "e1", "papel": "documento", "nome": "Editor de texto"}
            ]

            # primeira ação no Bloco de Notas: cartão "Precisa de você" de verdade
            acao = AcaoResolvida(acao=AcaoComputador(tipo="digitar", texto="Lista de compras"))
            agir = asyncio.create_task(computador.agir(acao))
            pedido = None
            for _ in range(100):
                lista = (await cliente.get("/v1/atencao", headers=a)).json()
                pedido = next((p for p in lista if p["acao"] == FERRAMENTA_PROGRAMA), None)
                if pedido:
                    break
                await asyncio.sleep(0.1)
            assert pedido is not None
            assert pedido["titulo"] == "Usar um programa do seu computador"
            assert "notepad.exe" in pedido["resumo"] and pedido["agente_id"] == bot["id"]
            # outra conta não decide
            decidir = f"/v1/aprovacoes/{pedido['id']}/decidir"
            assert (
                await cliente.post(decidir, json={"decisao": "permitir"}, headers=b)
            ).status_code == 404
            decidido = await cliente.post(decidir, json={"decisao": "sempre_permitir"}, headers=a)
            assert decidido.status_code == 204, decidido.text
            await asyncio.wait_for(agir, 15)
            assert app.permitidos_vistos == [[], ["notepad.exe"]]
            async with mundo.fabrica() as sessao_bd:
                regra = await sessao_bd.scalar(
                    select(RegraPermissao).where(RegraPermissao.ferramenta == FERRAMENTA_PROGRAMA)
                )
            assert regra is not None and regra.condicao == {"programa": "notepad.exe"}
            assert str(regra.agente_id) == bot["id"]

            # o mesmo comando não é respondido duas vezes; outra conta nem acha
            ultimo = app.recebidos[-1]["id"]
            url = f"/v1/computador-pc/comandos/{ultimo}/resultado"
            de_novo = await cliente.post(url, json={"sessao_id": sessao_id, "ok": True}, headers=da)
            assert de_novo.status_code == 409
            alheio = await cliente.post(
                url, json={"sessao_id": sessao_id, "ok": True}, headers={**b, **DESKTOP}
            )
            assert alheio.status_code == 404
            assert all(status == 204 for status in app.respostas_post)
            vez = (await cliente.get("/v1/computador-pc/estado", headers=a)).json()["vez"]
            assert vez["agente_id"] == bot["id"]

            # Entrada fisica entre comandos abre atencao imediatamente e sem duplicar.
            corpo_pausa = {"sessao_id": sessao_id, "agente_id": bot["id"]}
            for _ in range(2):
                pausa = await cliente.post("/v1/computador-pc/pausar", json=corpo_pausa, headers=da)
                assert pausa.status_code == 204, pausa.text
            atencao = (await cliente.get("/v1/atencao", headers=a)).json()
            assert (
                len([p for p in atencao if p["titulo"] == "Retomar o controle do computador?"]) == 1
            )

            # Parar na borda: o bot perde a vez e não volta logo
            parar = await cliente.post(
                "/v1/computador-pc/parar", json={"sessao_id": sessao_id}, headers=da
            )
            assert parar.status_code == 204
            with pytest.raises(ErroFerramenta, match=PARADO[:30]):
                await computador.observar()
            assert (await cliente.get("/v1/computador-pc/estado", headers=a)).json()["vez"] is None

            # outra sessão (outro PC) assume: a antiga recebe 409 no long-poll
            nova = await cliente.post("/v1/computador-pc/sessao", json=corpo, headers=da)
            assert nova.status_code == 200
            velha = await cliente.get(
                "/v1/computador-pc/comandos",
                params={"sessao_id": sessao_id, "espera": 0},
                headers=da,
            )
            assert velha.status_code == 409
            fim = await cliente.delete(
                f"/v1/computador-pc/sessao/{nova.json()['sessao_id']}", headers=da
            )
            assert fim.status_code == 204
            with pytest.raises(ErroFerramenta, match="app de desktop"):
                await provedor.obter(usuario_id, UUID(bot["id"]))
        finally:
            tarefa.cancel()
            await redis.aclose()
