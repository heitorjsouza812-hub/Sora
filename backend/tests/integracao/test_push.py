# ruff: noqa: F811
"""Notificação no celular com Postgres e Redis reais (API em uvicorn). O serviço de push de fora é
simulado (``_enviar_um``): o resto é o caminho de verdade."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app import push
from app.core.config import obter_configuracao
from app.modelos.tabelas import Agente, InscricaoPush
from tests.integracao.relogio_base import Mundo, mundo, servicos_relogio  # noqa: F401
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao

FCM = "https://fcm.googleapis.com/fcm/send/"


def _inscricao(sufixo: str) -> dict[str, Any]:
    return {"endpoint": FCM + sufixo, "keys": {"p256dh": "B" + "x" * 86, "auth": "a" * 22}}


async def test_inscrever_testar_e_limpar_aparelho_que_saiu(
    mundo: Mundo, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, "push-a@exemplo.com")
        assert (await cliente.get("/v1/push/chave", headers=auth)).json() == {"chave_publica": None}
        desligado = await cliente.post("/v1/push/inscricoes", headers=auth, json=_inscricao("a"))
        assert desligado.status_code == 503

        publica, privada = push.gerar_chaves()
        monkeypatch.setenv("VAPID_CHAVE_PUBLICA", publica)
        monkeypatch.setenv("VAPID_CHAVE_PRIVADA", privada)
        monkeypatch.setenv("VAPID_CONTATO", "mailto:suporte@exemplo.com")
        obter_configuracao.cache_clear()
        assert (await cliente.get("/v1/push/chave", headers=auth)).json()[
            "chave_publica"
        ] == publica

        ruim = {**_inscricao("b"), "endpoint": "https://10.0.0.5/push"}
        assert (
            await cliente.post("/v1/push/inscricoes", headers=auth, json=ruim)
        ).status_code == 422
        for sufixo in ("celular", "notebook"):
            r = await cliente.post("/v1/push/inscricoes", headers=auth, json=_inscricao(sufixo))
            assert r.status_code == 201, r.text
        # mesma inscrição de novo não duplica
        await cliente.post("/v1/push/inscricoes", headers=auth, json=_inscricao("celular"))

        enviados: list[tuple[str, str]] = []

        def servico_falso(inscricao: Any, carga: str, chave: str, contato: str) -> int:
            enviados.append((inscricao.endpoint, carga))
            assert chave == privada and contato == "mailto:suporte@exemplo.com"
            return 410 if inscricao.endpoint.endswith("notebook") else 201

        monkeypatch.setattr(push, "_enviar_um", servico_falso)
        teste = await cliente.post("/v1/push/teste", headers=auth)
        assert teste.json() == {"enviadas": 1}
        assert len(enviados) == 2
        async with mundo.fabrica() as sessao:
            restantes = (await sessao.scalars(select(InscricaoPush.endpoint))).all()
        assert restantes == [FCM + "celular"]  # o 410 apagou o aparelho que saiu

        # a carga de um pedido diz só quem precisa, e abre o cartão
        async with mundo.fabrica() as sessao:
            sora = await sessao.scalar(select(Agente).where(Agente.nome == "Sora"))
            assert sora is not None
            carga = await push.carga_do_pedido(sessao, "p1", "aprovacao", sora.id, None)
        assert carga == {
            "titulo": "Precisa de você",
            "corpo": "Sora precisa da sua aprovação.",
            "url": f"/bots/{sora.id}#pedido-p1",
            "tag": "pedido-p1",
        }

        apagou = await cliente.request(
            "DELETE", "/v1/push/inscricoes", headers=auth, json={"endpoint": FCM + "celular"}
        )
        assert apagou.status_code == 204
        async with mundo.fabrica() as sessao:
            assert await sessao.scalar(select(func.count(InscricaoPush.id))) == 0
