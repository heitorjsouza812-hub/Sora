# ruff: noqa: F811
"""Vela-12: "Permitir" no cartão de retomar volta o MESMO turno, com API, Postgres e Redis reais.

Teste do Heitor (2026-11-15): o cartão "Retomar o controle do computador?" nascia sem conversa
(rota ``/pausar``); o bot esperava 90 s dentro da ferramenta e desistia, e o "Permitir" que vinha
depois não retomava nada. Agora: pausa → cartão → o turno pausa (``interrupt``) com o cartão ligado
à conversa → ``POST /decidir`` põe na fila ``retomar_conversa`` → a ferramenta roda de novo, manda
``retomar`` à ponte e segue.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
import pytest
from redis.asyncio import Redis

from app.computador import pc_usuario as modulo_pc
from app.computador.pc_usuario import ProvedorPcUsuario
from app.ferramentas.base import ContextoFerramenta
from app.modelos.tabelas import Aprovacao, Conversa
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_computador_pc import AppDesktop, entrar_desktop
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao


class TurnoPausado(Exception):
    def __init__(self, valor: dict) -> None:
        super().__init__(valor)
        self.valor = valor


@pytest.fixture(autouse=True)
def _fila_limpa():
    from workers.fila import configurar_fila

    configurar_fila(None)
    yield
    configurar_fila(None)


async def test_pausa_cartao_permitir_retoma_o_turno(mundo: Mundo, monkeypatch) -> None:
    def interromper(valor: dict) -> None:
        raise TurnoPausado(valor)

    monkeypatch.setattr(modulo_pc, "_interromper", interromper)
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        a = await entrar(cliente, mundo.fabrica, "vela12-a@exemplo.com")
        bot = (await cliente.post("/v1/agentes", json={"descricao": "Planilhas"}, headers=a)).json()
        da, renovacao = await entrar_desktop(cliente, "vela12-a@exemplo.com")
        corpo = {"dispositivo": "PC", "autorizados": [bot["id"]], "token_renovacao": renovacao}
        sessao = (await cliente.post("/v1/computador-pc/sessao", json=corpo, headers=da)).json()
        usuario_id, bot_id = UUID(sessao["usuario_id"]), UUID(bot["id"])
        async with mundo.fabrica() as bd:
            conversa = Conversa(usuario_id=usuario_id, agente_id=bot_id, titulo="Excel")
            bd.add(conversa)
            await bd.commit()
            conversa_id = conversa.id

        redis = Redis.from_url(mundo.url_redis, decode_responses=True)
        provedor = ProvedorPcUsuario(redis=redis)
        app = AppDesktop(cliente, da, sessao["sessao_id"])
        tarefa = asyncio.create_task(app.rodar())

        async def chamada() -> modulo_pc.ComputadorPcUsuario:
            """Cada chamada de ferramenta do worker cria o seu (como ``servico._computador``)."""
            pc = await provedor.obter(usuario_id, bot_id)
            pc.contexto = ContextoFerramenta(
                usuario_id=usuario_id, agente_id=bot_id, conversa_id=conversa_id
            )
            return pc

        try:
            await (await chamada()).observar()  # o bot pega a vez

            # o usuário mexe no mouse entre um comando e outro: a ponte chama /pausar
            pausa = await cliente.post(
                "/v1/computador-pc/pausar",
                json={"sessao_id": sessao["sessao_id"], "agente_id": bot["id"]},
                headers=da,
            )
            assert pausa.status_code == 204, pausa.text

            # próxima ferramenta do bot: o turno pausa no cartão (antes: esperava 90 s e desistia)
            with pytest.raises(TurnoPausado) as pausado:
                await (await chamada()).observar()
            aprovacao_id = UUID(pausado.value.valor["aprovacao_id"])
            async with mundo.fabrica() as bd:
                cartao = await bd.get(Aprovacao, aprovacao_id)
                assert cartao is not None and cartao.acao["tipo"] == "pc_retomar"
                assert cartao.acao["conversa_id"] == str(conversa_id)  # ligado ao turno

            # o usuário decide pela Sora: a vez está solta e o bot pausado, então não há 409
            decidido = await cliente.post(
                f"/v1/aprovacoes/{aprovacao_id}/decidir",
                json={"decisao": "permitir_uma_vez"},
                headers=a,
            )
            assert decidido.status_code == 204, decidido.text
            assert await redis.exists(f"arq:job:aprovacao:{aprovacao_id}")  # retomar_conversa

            # a retomada roda a ferramenta de novo: manda "retomar" à ponte e segue
            antes = len(app.recebidos)
            observacao = await (await chamada()).observar()
            assert observacao.janelas[0].programa == "notepad.exe"
            assert [c["operacao"] for c in app.recebidos[antes:]] == ["retomar", "observar"]
            estado = (await cliente.get("/v1/computador-pc/estado", headers=a)).json()
            assert estado["vez"]["agente_id"] == bot["id"]
        finally:
            tarefa.cancel()
            await redis.aclose()
