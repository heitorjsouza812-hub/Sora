"""Robustez da Fase B (rodada 4): o que o validador provou que quebrava.

Postgres e Redis reais, API em uvicorn, worker ARQ real. Dois tipos de modelo: o falso
(``SORA_MODELO_FALSO=1``) e um provedor HTTP local que o teste controla resposta a resposta
(erro 500, texto sem plano, chamadas de ferramenta roteirizadas).
"""

# ruff: noqa: F401, F811
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from arq.connections import RedisSettings, create_pool
from arq.worker import create_worker
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agentes.aparencia import NOMES_AGENTES, PALETA_AGENTES
from app.core.banco import fabrica_sessoes
from app.core.config import obter_configuracao
from app.ferramentas import ambiente
from app.main import criar_aplicacao
from app.modelos.enumeracoes import (
    AutorMensagem,
    DecisaoAprovacao,
    Movimento,
    StatusAprovacao,
    StatusCadeia,
    StatusEtapa,
    TipoAgente,
    TipoConversa,
    TipoProvedor,
)
from app.modelos.tabelas import (
    Agente,
    Aprovacao,
    Cadeia,
    Conversa,
    Etapa,
    Mensagem,
    ModeloDisponivel,
    Passo,
    Pergunta,
    Provedor,
    Usuario,
)
from tests.integracao.test_fase_b_pronto import (
    _porta_livre,
    ambiente_fase_b,
    ambiente_fase_b_arq,
    entrar,
    ler_sse,
    servicos_fase_b,
)
from workers.configuracao import WorkerSettings

pytestmark = pytest.mark.integracao

RAIZ = Path(__file__).resolve().parents[2]
LIMITE_S = 40


async def esperar(condicao: Callable[[], Any], descricao: str, limite_s: float = LIMITE_S) -> Any:
    """Repete ``condicao`` (corrotina) até devolver algo verdadeiro."""
    for _ in range(int(limite_s * 5)):
        valor = await condicao()
        if valor:
            return valor
        await asyncio.sleep(0.2)
    pytest.fail(f"tempo esgotado: {descricao}")


# ---------------------------------------------------------------- modelo falso: passos, cores


async def test_passos_cores_esgotadas_e_last_event_id_invalido(
    ambiente_fase_b_arq: tuple[str, async_sessionmaker],
) -> None:
    url, fabrica = ambiente_fase_b_arq
    async with httpx.AsyncClient(base_url=url, timeout=30) as cliente:
        auth = await entrar(cliente, fabrica, "robustez-cores@exemplo.com")
        async with fabrica() as sessao:
            usuario = await sessao.scalar(
                select(Usuario).where(Usuario.email == "robustez-cores@exemplo.com")
            )
            # B1: o usuário já tem todos os nomes e todas as cores da paleta em uso
            for i, nome in enumerate(NOMES_AGENTES):
                sessao.add(
                    Agente(
                        usuario_id=usuario.id,
                        tipo=TipoAgente.INDIVIDUAL,
                        nome=nome,
                        funcao="teste",
                        papel="teste",
                        cor=PALETA_AGENTES[i % len(PALETA_AGENTES)],
                        movimento=Movimento.GIRA,
                        nivel_padrao="N1",
                        ferramentas=[],
                    )
                )
            await sessao.commit()

        resposta = await cliente.post(
            "/v1/conversas",
            headers=auth,
            json={"texto": "crie uma campanha para minha cafeteria", "anexos": []},
        )
        assert resposta.status_code == 201, resposta.text
        conversa_id = resposta.json()["id"]
        eventos = await ler_sse(
            cliente,
            conversa_id,
            auth,
            ate=lambda n, d: (
                n == "cadeia.atualizada" and d.get("status") in {"concluida", "falhou"}
            ),
        )
        final = [d for n, d in eventos if n == "cadeia.atualizada"][-1]
        assert final["status"] == "concluida", final
        nomes = [n for n, _ in eventos]
        # Vitral: o painel Trabalho precisa dos eventos `passo`, e eles ficam gravados
        assert "passo" in nomes
        passos = [d for n, d in eventos if n == "passo"]
        assert {p["status"] for p in passos} >= {"executando", "concluido"}
        async with fabrica() as sessao:
            assert (await sessao.scalar(select(Passo.id).limit(1))) is not None
            criados = (
                await sessao.scalars(
                    select(Agente.nome).where(
                        Agente.usuario_id == usuario.id, Agente.cadeia_id.is_not(None)
                    )
                )
            ).all()
            assert len(criados) == 3 and not set(criados) & set(NOMES_AGENTES)
            cores = (
                await sessao.scalars(
                    select(Agente.cor).where(
                        Agente.usuario_id == usuario.id, Agente.cadeia_id.is_not(None)
                    )
                )
            ).all()
            assert "#E2ECFF" not in {c.upper() for c in cores}

        # B4: Last-Event-ID corrompido é 400, não um stream vazio em silêncio
        for invalido in ("abc", "-1", "1-1; DROP", "x" * 500):
            ruim = await cliente.get(
                f"/v1/conversas/{conversa_id}/eventos",
                headers={**auth, "Last-Event-ID": invalido},
            )
            assert ruim.status_code == 400, (invalido, ruim.status_code)
            assert "Last-Event-ID" in ruim.json()["detail"]


# ---------------------------------------------------------------- provedor HTTP controlável


@dataclass
class ProvedorFalso:
    """Servidor compatível com OpenAI; ``responder(corpo, n)`` devolve corpo ou (status, corpo)."""

    responder: Callable[[dict[str, Any], int], Any]
    chamadas: list[dict[str, Any]] = field(default_factory=list)


def completar_texto(texto: str) -> dict[str, Any]:
    return _completacao({"role": "assistant", "content": texto}, "stop")


def completar_ferramenta(nome: str, argumentos: dict[str, Any]) -> dict[str, Any]:
    mensagem = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call-{nome}",
                "type": "function",
                "function": {"name": nome, "arguments": json.dumps(argumentos)},
            }
        ],
    }
    return _completacao(mensagem, "tool_calls")


def _completacao(mensagem: dict[str, Any], motivo: str) -> dict[str, Any]:
    return {
        "id": "local",
        "object": "chat.completion",
        "created": 1,
        "model": "modelo-local",
        "choices": [{"index": 0, "message": mensagem, "finish_reason": motivo}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    }


@dataclass
class AmbienteHttp:
    url_api: str
    url_redis: str
    fabrica: async_sessionmaker
    provedor: ProvedorFalso
    redis: Redis
    provedor_url: str


@pytest.fixture
async def ambiente_http(
    servicos_fase_b: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AmbienteHttp]:
    url_pg, url_redis = servicos_fase_b
    provedor = ProvedorFalso(responder=lambda corpo, n: completar_texto("ok"))
    api_modelo = FastAPI()

    @api_modelo.post("/v1/chat/completions")
    async def completar(requisicao: Request) -> JSONResponse:
        corpo = await requisicao.json()
        provedor.chamadas.append(corpo)
        resultado = provedor.responder(corpo, len(provedor.chamadas))
        if isinstance(resultado, tuple):
            return JSONResponse(resultado[1], status_code=resultado[0])
        return JSONResponse(resultado)

    porta_modelo = _porta_livre()
    servidor_modelo = uvicorn.Server(
        uvicorn.Config(
            api_modelo, host="127.0.0.1", port=porta_modelo, log_level="warning", lifespan="off"
        )
    )
    tarefa_modelo = asyncio.create_task(servidor_modelo.serve())
    while not servidor_modelo.started:  # noqa: ASYNC110
        await asyncio.sleep(0.05)

    monkeypatch.setattr(signal, "SIGUSR1", signal.SIGTERM, raising=False)
    monkeypatch.setenv("AMBIENTE", "teste")
    monkeypatch.setenv("SORA_MODELO_FALSO", "0")
    monkeypatch.setenv("PERMITIR_PROVEDOR_REDE_LOCAL", "1")
    monkeypatch.setenv("BUSCA_PROVEDOR", "falso")
    monkeypatch.setenv("DATABASE_URL", url_pg)
    monkeypatch.setenv("REDIS_URL", url_redis)
    obter_configuracao.cache_clear()
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()

    alembic = Config(str(RAIZ / "alembic.ini"))
    alembic.set_main_option("script_location", str(RAIZ / "migrations"))
    await asyncio.to_thread(command.upgrade, alembic, "head")
    redis = Redis.from_url(url_redis, decode_responses=True)
    await redis.flushdb()
    motor = create_async_engine(url_pg)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as sessao:
        await sessao.execute(text("delete from convites where codigo = 'FASE-B'"))
        await sessao.execute(
            text("insert into convites (codigo, usos_restantes) values ('FASE-B', 50)")
        )
        await sessao.commit()
    porta_api = _porta_livre()
    servidor_api = uvicorn.Server(
        uvicorn.Config(
            criar_aplicacao(), host="127.0.0.1", port=porta_api, log_level="warning", lifespan="on"
        )
    )
    tarefa_api = asyncio.create_task(servidor_api.serve())
    while not servidor_api.started:  # noqa: ASYNC110
        await asyncio.sleep(0.05)
    worker = create_worker(
        WorkerSettings,
        redis_settings=RedisSettings.from_dsn(url_redis),
        handle_signals=False,
        poll_delay=0.1,
    )
    tarefa_worker = asyncio.create_task(worker.async_run())
    try:
        yield AmbienteHttp(
            f"http://127.0.0.1:{porta_api}",
            url_redis,
            fabrica,
            provedor,
            redis,
            f"http://127.0.0.1:{porta_modelo}/v1",
        )
    finally:
        await worker.close()
        tarefa_worker.cancel()
        servidor_api.should_exit = True
        await tarefa_api
        servidor_modelo.should_exit = True
        await tarefa_modelo
        await redis.aclose()
        await motor.dispose()
        obter_configuracao.cache_clear()
        fabrica_sessoes.cache_clear()
        ambiente.redis_dos_eventos.cache_clear()


async def usuario_com_modelo_http(
    amb: AmbienteHttp, cliente: httpx.AsyncClient, email: str
) -> tuple[dict[str, str], UUID]:
    """Cadastra o usuário e aponta o provedor dele para o servidor HTTP local."""
    cadastro = await cliente.post(
        "/v1/auth/cadastrar",
        json={"nome": "Ana", "email": email, "senha": "uma-senha-bem-longa", "convite": "FASE-B"},
    )
    assert cadastro.status_code == 201, cadastro.text
    login = await cliente.post(
        "/v1/auth/entrar", json={"email": email, "senha": "uma-senha-bem-longa"}
    )
    auth = {"Authorization": f"Bearer {login.json()['token_acesso']}"}
    async with amb.fabrica() as sessao:
        usuario = await sessao.scalar(select(Usuario).where(Usuario.email == email))
        provedor = Provedor(
            usuario_id=usuario.id,
            tipo=TipoProvedor.COMPATIVEL_OPENAI,
            base_url=amb.provedor_url,
            validado_em=datetime.now(UTC),
        )
        sessao.add(provedor)
        await sessao.flush()
        sessao.add(
            ModeloDisponivel(
                provedor_id=provedor.id,
                modelo="openai/modelo-local",
                nivel="N2",
                capacidades=["ferramentas", "json"],
                contexto=32_000,
                velocidade_tps=100,
            )
        )
        await sessao.commit()
        return auth, usuario.id


async def _conversa_com_pedido(
    amb: AmbienteHttp, usuario_id: UUID, texto: str
) -> tuple[UUID, UUID]:
    """Conversa direta com a Sora e a mensagem do usuário (sem passar pela triagem)."""
    async with amb.fabrica() as sessao:
        sora = await sessao.scalar(
            select(Agente).where(Agente.usuario_id == usuario_id, Agente.tipo == TipoAgente.SORA)
        )
        conversa = Conversa(
            usuario_id=usuario_id, agente_id=sora.id, tipo=TipoConversa.CHAT, titulo="teste"
        )
        sessao.add(conversa)
        await sessao.flush()
        mensagem = Mensagem(
            conversa_id=conversa.id,
            autor=AutorMensagem.USUARIO,
            conteudo=texto,
            anexos=[],
            visivel=True,
        )
        sessao.add(mensagem)
        await sessao.commit()
        return conversa.id, mensagem.id


async def _enfileirar(url_redis: str, job: str, *args: Any) -> None:
    fila = await create_pool(RedisSettings.from_dsn(url_redis))
    try:
        await fila.enqueue_job(job, *args)
    finally:
        await fila.aclose()


async def _cadeia_e_etapa(
    fabrica: async_sessionmaker, usuario_id: UUID, status: StatusCadeia
) -> tuple[UUID, UUID, UUID]:
    """Cadeia com uma etapa pendente (pesquisador) e o agente dela."""
    async with fabrica() as sessao:
        sora = await sessao.scalar(
            select(Agente).where(Agente.usuario_id == usuario_id, Agente.tipo == TipoAgente.SORA)
        )
        conversa = Conversa(
            usuario_id=usuario_id, agente_id=sora.id, tipo=TipoConversa.PROJETO, titulo="cadeia"
        )
        sessao.add(conversa)
        await sessao.flush()
        pedido = Mensagem(
            conversa_id=conversa.id,
            autor=AutorMensagem.USUARIO,
            conteudo="Pesquise cafeterias da região.",
            anexos=[],
            visivel=True,
        )
        sessao.add(pedido)
        await sessao.flush()
        cadeia = Cadeia(
            usuario_id=usuario_id,
            conversa_id=conversa.id,
            pedido_id=pedido.id,
            status=status,
            plano={
                "objetivo": "Pesquisar",
                "requisitos": ["Lista de cafeterias"],
                "etapas": [{"ordem": 1, "pronto_quando": "Lista pronta"}],
            },
            orcamento_tokens=50_000,
        )
        sessao.add(cadeia)
        await sessao.flush()
        agente = Agente(
            usuario_id=usuario_id,
            tipo=TipoAgente.ESPECIALISTA,
            nome="Atlas",
            funcao="Pesquisa",
            papel="pesquisador",
            cor=PALETA_AGENTES[0],
            movimento=Movimento.VIBRACAO,
            nivel_padrao="N2",
            ferramentas=[],
            cadeia_id=cadeia.id,
        )
        sessao.add(agente)
        await sessao.flush()
        etapa = Etapa(
            cadeia_id=cadeia.id,
            ordem=1,
            depende_de=[],
            especialista="pesquisador",
            agente_id=agente.id,
            titulo="Pesquisar",
            nivel="N2",
            tarefa="Pesquise cafeterias da região.",
            status=StatusEtapa.PENDENTE,
        )
        sessao.add(etapa)
        await sessao.commit()
        return conversa.id, cadeia.id, etapa.id


async def test_erro_do_provedor_na_triagem_nao_perde_o_texto(ambiente_http: AmbienteHttp) -> None:
    """B3: provedor com 500/401/429/lixo -> 201, mensagem guardada e aviso em PT-BR (não 500)."""
    amb = ambiente_http
    respostas: list[Any] = [
        (500, {"error": {"message": "sk-VAZOU-123 quebrou"}}),
        (401, {"error": {"message": "chave inválida"}}),
        (429, {"error": {"message": "limite"}}),
        (200, {"lixo": "isto não é uma completação"}),
    ]
    async with httpx.AsyncClient(base_url=amb.url_api, timeout=60) as cliente:
        auth, _ = await usuario_com_modelo_http(amb, cliente, "triagem-erro@exemplo.com")
        for i, resposta_do_provedor in enumerate(respostas):
            amb.provedor.responder = lambda corpo, n, r=resposta_do_provedor: r
            texto = f"crie uma campanha para a cafeteria {i}"
            resposta = await cliente.post(
                "/v1/conversas", headers=auth, json={"texto": texto, "anexos": []}
            )
            assert resposta.status_code == 201, (i, resposta.status_code, resposta.text)
            conversa_id = resposta.json()["id"]
            mensagens = await cliente.get(f"/v1/conversas/{conversa_id}/mensagens", headers=auth)
            conteudos = [m["conteudo"] for m in mensagens.json()]
            assert texto in conteudos
            assert any("Não consegui falar com o seu modelo" in c for c in conteudos), conteudos
            assert "sk-VAZOU-123" not in resposta.text + mensagens.text


async def test_planejador_com_erro_vira_falhou_com_evento(ambiente_http: AmbienteHttp) -> None:
    """B1: planejar_cadeia nunca fica preso em `planejando`: plano inválido -> `falhou`."""
    amb = ambiente_http
    amb.provedor.responder = lambda corpo, n: completar_texto("não sei planejar isso")
    async with httpx.AsyncClient(base_url=amb.url_api, timeout=60) as cliente:
        auth, usuario_id = await usuario_com_modelo_http(amb, cliente, "planejador@exemplo.com")
        conversa_id, cadeia_id, _ = await _cadeia_e_etapa(
            amb.fabrica, usuario_id, StatusCadeia.PLANEJANDO
        )
        await _enfileirar(amb.url_redis, "planejar_cadeia", str(cadeia_id))
        eventos = await ler_sse(
            cliente,
            str(conversa_id),
            auth,
            ate=lambda n, d: n == "cadeia.atualizada" and d["status"] == "falhou",
            limite_s=LIMITE_S,
        )
        assert eventos
    async with amb.fabrica() as sessao:
        assert (await sessao.get(Cadeia, cadeia_id)).status == StatusCadeia.FALHOU


async def test_erro_do_provedor_dentro_da_etapa(ambiente_http: AmbienteHttp) -> None:
    """Provedor 500 no meio da etapa: etapa `falhou`, cadeia `falhou`, evento para o app."""
    amb = ambiente_http
    amb.provedor.responder = lambda corpo, n: (500, {"error": {"message": "indisponível"}})
    async with httpx.AsyncClient(base_url=amb.url_api, timeout=60) as cliente:
        auth, usuario_id = await usuario_com_modelo_http(amb, cliente, "etapa-erro@exemplo.com")
        conversa_id, cadeia_id, etapa_id = await _cadeia_e_etapa(
            amb.fabrica, usuario_id, StatusCadeia.EXECUTANDO
        )
        await _enfileirar(amb.url_redis, "executar_etapa", str(etapa_id))
        eventos = await ler_sse(
            cliente,
            str(conversa_id),
            auth,
            ate=lambda n, d: n == "cadeia.atualizada" and d["status"] == "falhou",
        )
        etapas = [d for n, d in eventos if n == "etapa.atualizada"]
        assert any(e["status"] == "falhou" for e in etapas)
    async with amb.fabrica() as sessao:
        etapa = await sessao.get(Etapa, etapa_id)
        assert etapa.status == StatusEtapa.FALHOU and etapa.erro
        assert (await sessao.get(Cadeia, cadeia_id)).status == StatusCadeia.FALHOU


async def test_pergunta_fora_de_cadeia_retoma_a_conversa(ambiente_http: AmbienteHttp) -> None:
    """Achado 6: a Sora pergunta numa conversa comum; a resposta acorda a conversa."""
    amb = ambiente_http

    def roteiro(corpo: dict[str, Any], n: int) -> Any:
        if n == 1:
            return completar_ferramenta(
                "perguntar",
                {
                    "texto": "Qual tom?",
                    "opcoes": [
                        {"rotulo": "Formal", "valor": "formal"},
                        {"rotulo": "Leve", "valor": "leve"},
                    ],
                },
            )
        return completar_texto("Combinado, vou no tom leve.")

    amb.provedor.responder = roteiro
    async with httpx.AsyncClient(base_url=amb.url_api, timeout=60) as cliente:
        auth, usuario_id = await usuario_com_modelo_http(amb, cliente, "pergunta-sora@exemplo.com")
        conversa_id, mensagem_id = await _conversa_com_pedido(amb, usuario_id, "Escreva um texto")
        await _enfileirar(amb.url_redis, "responder_direto", str(mensagem_id))

        async def pergunta() -> Pergunta | None:
            async with amb.fabrica() as sessao:
                return await sessao.scalar(
                    select(Pergunta).where(Pergunta.conversa_id == conversa_id)
                )

        achada = await esperar(pergunta, "a Sora não perguntou")
        resposta = await cliente.post(
            f"/v1/perguntas/{achada.id}/responder", headers=auth, json={"valor": "leve"}
        )
        assert resposta.status_code == 204, resposta.text

        async def falou() -> bool:
            async with amb.fabrica() as sessao:
                textos = (
                    await sessao.scalars(
                        select(Mensagem.conteudo).where(
                            Mensagem.conversa_id == conversa_id, Mensagem.autor == "sora"
                        )
                    )
                ).all()
            return any("tom leve" in t for t in textos)

        await esperar(falou, "a conversa não retomou depois da resposta")
        # retomou de verdade: a 2ª chamada ao modelo traz a resposta como resultado da ferramenta
        papeis = [m["role"] for m in amb.provedor.chamadas[-1]["messages"]]
        assert "tool" in papeis
        assert any("leve" in str(m.get("content")) for m in amb.provedor.chamadas[-1]["messages"])


async def _aprovacao_da_sora(amb: AmbienteHttp, usuario_id: UUID) -> Aprovacao:
    def roteiro(corpo: dict[str, Any], n: int) -> Any:
        if n == 1:
            return completar_ferramenta("criar_agente", {"nome": "Íris", "papel": "Organizar"})
        return completar_texto("Entendi, sigo sem criar.")

    amb.provedor.responder = roteiro
    conversa_id, mensagem_id = await _conversa_com_pedido(amb, usuario_id, "Crie a Íris")
    await _enfileirar(amb.url_redis, "responder_direto", str(mensagem_id))

    async def cartao() -> Aprovacao | None:
        async with amb.fabrica() as sessao:
            return await sessao.scalar(select(Aprovacao).where(Aprovacao.usuario_id == usuario_id))

    achado = await esperar(cartao, "o cartão de aprovação não apareceu")

    async def pausa_gravada() -> bool:
        # o cartão aparece antes de o checkpoint da pausa ser gravado; decidir antes disso
        # retomaria um thread sem a pausa
        async with amb.fabrica() as sessao:
            return bool(
                await sessao.scalar(
                    text("select count(*) from checkpoint_writes where channel = '__interrupt__'")
                )
            )

    await esperar(pausa_gravada, "a pausa não foi gravada no checkpoint")
    assert achado.etapa_id is None and achado.acao["conversa_id"] == str(conversa_id)
    return achado


async def test_aprovacao_fora_de_cadeia_retoma_a_conversa(ambiente_http: AmbienteHttp) -> None:
    amb = ambiente_http
    async with httpx.AsyncClient(base_url=amb.url_api, timeout=60) as cliente:
        auth, usuario_id = await usuario_com_modelo_http(amb, cliente, "aprova-sora@exemplo.com")
        cartao = await _aprovacao_da_sora(amb, usuario_id)
        resposta = await cliente.post(
            f"/v1/aprovacoes/{cartao.id}/decidir",
            headers=auth,
            json={"decisao": DecisaoAprovacao.PERMITIR_UMA_VEZ.value},
        )
        assert resposta.status_code == 204, resposta.text

        async def criou() -> bool:
            async with amb.fabrica() as sessao:
                return (
                    await sessao.scalar(
                        select(Agente.id).where(
                            Agente.usuario_id == usuario_id, Agente.nome == "Íris"
                        )
                    )
                ) is not None

        await esperar(criou, "a conversa não retomou e não criou o agente")


async def test_aprovacao_expirada_nega_e_retoma(ambiente_http: AmbienteHttp) -> None:
    """Achado 7: `expirar_aprovacao` marca `expirada`, avisa o app e retoma com "negado"."""
    amb = ambiente_http
    async with httpx.AsyncClient(base_url=amb.url_api, timeout=60) as cliente:
        _, usuario_id = await usuario_com_modelo_http(amb, cliente, "expira@exemplo.com")
        cartao = await _aprovacao_da_sora(amb, usuario_id)
        async with amb.fabrica() as sessao:
            await sessao.execute(
                text("update aprovacoes set expira_em = now() - interval '1 minute' where id = :i"),
                {"i": cartao.id},
            )
            await sessao.commit()
        await _enfileirar(amb.url_redis, "expirar_aprovacao", str(cartao.id))

        async def expirou() -> bool:
            async with amb.fabrica() as sessao:
                return (await sessao.get(Aprovacao, cartao.id)).status == StatusAprovacao.EXPIRADA

        await esperar(expirou, "a aprovação não expirou")

        async def retomou() -> bool:
            async with amb.fabrica() as sessao:
                textos = (
                    await sessao.scalars(select(Mensagem.conteudo).where(Mensagem.autor == "sora"))
                ).all()
            return any("sigo sem criar" in t for t in textos)

        await esperar(retomou, "a conversa não retomou depois de expirar")
        async with amb.fabrica() as sessao:
            assert (
                await sessao.scalar(
                    select(Agente.id).where(Agente.usuario_id == usuario_id, Agente.nome == "Íris")
                )
            ) is None


# ---------------------------------------------------------------- worker morto de verdade


def _ler_ate_travar(processo: subprocess.Popen) -> str:
    saida = []
    for linha in processo.stdout:  # type: ignore[union-attr]
        saida.append(linha)
        if "TRAVADO-NA-ETAPA" in linha:
            return linha
    raise AssertionError("o worker lento terminou sem travar:\n" + "".join(saida[-30:]))


async def test_worker_morto_no_meio_da_etapa_e_retomado_pelo_reconciliador(
    ambiente_fase_b: tuple[Any, async_sessionmaker, Redis],
    servicos_fase_b: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B2: um processo worker separado trava na etapa e é MORTO (kill). Um worker saudável
    sobe, o reconciliador devolve a etapa para a fila uma vez e a cadeia conclui."""
    _, url_redis = servicos_fase_b
    cliente, fabrica, redis = ambiente_fase_b
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()
    auth = await entrar(cliente, fabrica, "worker-morto@exemplo.com")
    resposta = await cliente.post(
        "/v1/conversas",
        headers=auth,
        json={"texto": "crie uma campanha para minha cafeteria", "anexos": []},
    )
    assert resposta.status_code == 201, resposta.text
    conversa_id = resposta.json()["id"]

    # o cron do reconciliador está registrado no WorkerSettings
    assert any(j.name.endswith("reconciliar_travados") for j in WorkerSettings.cron_jobs)

    script = RAIZ / "tests" / "integracao" / "auxiliares" / "worker_lento.py"
    processo = subprocess.Popen(  # noqa: ASYNC220
        [sys.executable, str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    try:
        linha = await asyncio.wait_for(asyncio.to_thread(_ler_ate_travar, processo), timeout=90)
        assert "TRAVADO-NA-ETAPA" in linha
        async with fabrica() as sessao:
            cadeia = await sessao.scalar(select(Cadeia).where(Cadeia.conversa_id == conversa_id))
            travada = await sessao.scalar(
                select(Etapa).where(
                    Etapa.cadeia_id == cadeia.id, Etapa.status == StatusEtapa.EXECUTANDO
                )
            )
            assert travada is not None
            etapa_id, cadeia_id = travada.id, cadeia.id
    finally:
        processo.kill()  # morte de verdade: nada de desligamento limpo
        processo.wait(timeout=30)

    # passou muito tempo desde que a etapa começou
    async with fabrica() as sessao:
        await sessao.execute(
            text("update etapas set iniciada_em = now() - interval '10 minutes' where id = :i"),
            {"i": etapa_id},
        )
        await sessao.commit()

    monkeypatch.setattr(signal, "SIGUSR1", signal.SIGTERM, raising=False)
    saudavel = create_worker(
        WorkerSettings,
        redis_settings=RedisSettings.from_dsn(url_redis),
        handle_signals=False,
        poll_delay=0.1,
    )
    tarefa = asyncio.create_task(saudavel.async_run())
    try:
        await _enfileirar(url_redis, "reconciliar_travados")

        async def concluiu() -> bool:
            async with fabrica() as sessao:
                return (await sessao.get(Cadeia, cadeia_id)).status == StatusCadeia.CONCLUIDA

        await esperar(concluiu, "a cadeia não concluiu depois da retomada", limite_s=90)
        assert await redis.get(f"retomadas:{etapa_id}") == "1"
        async with fabrica() as sessao:
            assert (await sessao.get(Etapa, etapa_id)).status == StatusEtapa.CONCLUIDA
    finally:
        await saudavel.close()
        tarefa.cancel()


async def test_segunda_queda_falha_a_etapa_e_a_cadeia(
    ambiente_fase_b: tuple[Any, async_sessionmaker, Redis],
) -> None:
    """Depois de uma retomada, a próxima queda não retoma: etapa e cadeia `falhou`, com evento."""
    from app.eventos.streams import canal_conversa
    from workers.travados import reconciliar_travados

    cliente, fabrica, redis = ambiente_fase_b
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()
    await entrar(cliente, fabrica, "segunda-queda@exemplo.com")
    async with fabrica() as sessao:
        usuario = await sessao.scalar(
            select(Usuario).where(Usuario.email == "segunda-queda@exemplo.com")
        )
    conversa_id, cadeia_id, etapa_id = await _cadeia_e_etapa(
        fabrica, usuario.id, StatusCadeia.EXECUTANDO
    )
    async with fabrica() as sessao:
        await sessao.execute(
            text(
                "update etapas set status = 'executando', "
                "iniciada_em = now() - interval '10 minutes' where id = :i"
            ),
            {"i": etapa_id},
        )
        await sessao.commit()
    await redis.set(f"retomadas:{etapa_id}", 1)
    resultado = await reconciliar_travados({"sessoes": fabrica, "redis_eventos": redis})
    assert resultado == {"retomadas": 0, "falhas": 1}
    async with fabrica() as sessao:
        etapa = await sessao.get(Etapa, etapa_id)
        assert etapa.status == StatusEtapa.FALHOU and "parou duas vezes" in etapa.erro
        assert (await sessao.get(Cadeia, cadeia_id)).status == StatusCadeia.FALHOU
    eventos = [
        (c["event"], json.loads(c["data"]))
        for _, c in await redis.xrange(canal_conversa(conversa_id))
    ]
    assert ("cadeia.atualizada", "falhou") in [(n, d.get("status")) for n, d in eventos]


# ---------------------------------------------------------------- motor: verificador, ajuste, tool


def _ctx_com_modelo(fabrica, redis, modelos_por_papel):
    from langgraph.checkpoint.memory import InMemorySaver

    return {
        "sessoes": fabrica,
        "redis_eventos": redis,
        "checkpointer": InMemorySaver(),
        "modelos_da_etapa": modelos_por_papel,
    }


async def _cadeia_para_verificar(fabrica, usuario_id: UUID) -> tuple[UUID, UUID]:
    """Cadeia `executando` com a etapa de trabalho concluída (N2) e o Verificador pendente."""
    conversa_id, cadeia_id, etapa_id = await _cadeia_e_etapa(
        fabrica, usuario_id, StatusCadeia.EXECUTANDO
    )
    async with fabrica() as sessao:
        trabalho = await sessao.get(Etapa, etapa_id)
        trabalho.status = StatusEtapa.CONCLUIDA
        verificador_agente = Agente(
            usuario_id=usuario_id,
            tipo=TipoAgente.ESPECIALISTA,
            nome="Vera",
            funcao="Verificação",
            papel="verificador",
            cor=PALETA_AGENTES[1],
            movimento=Movimento.GIRA,
            nivel_padrao="N2",
            ferramentas=[],
            cadeia_id=cadeia_id,
        )
        sessao.add(verificador_agente)
        await sessao.flush()
        sessao.add(
            Etapa(
                cadeia_id=cadeia_id,
                ordem=2,
                depende_de=[1],
                especialista="verificador",
                agente_id=verificador_agente.id,
                titulo="Verificar",
                nivel="N2",
                tarefa="Confira o resultado.",
                status=StatusEtapa.PENDENTE,
            )
        )
        await sessao.commit()
    return conversa_id, cadeia_id


def _modelo_do_veredito(aprovado: bool):
    from tests.integracao.test_compasso_agente import _chamada, _modelo_roteirizado

    args = {
        "aprovado": aprovado,
        "requisitos": [
            {
                "requisito": "Lista de cafeterias",
                "evidencia": "veio incompleta",
                "status": "atendido" if aprovado else "parcial",
            }
        ],
        "motivo": "ok" if aprovado else "faltou completar a lista",
    }
    return _modelo_roteirizado([_chamada("veredito", args)])


async def test_reprovacao_sobe_para_n3_uma_vez_e_depois_falha(
    ambiente_fase_b: tuple[Any, async_sessionmaker, Redis],
) -> None:
    """Achado 11 (§6): 1ª reprovação = nova tentativa em N3; 2ª = cadeia `falhou`, com evento.
    Achado 3: erro do Verificador também vira `falhou` (não fica em `verificando`)."""
    from app.eventos.streams import canal_conversa
    from workers.cadeia import verificar_cadeia

    cliente, fabrica, redis = ambiente_fase_b
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()
    await entrar(cliente, fabrica, "reprova@exemplo.com")
    async with fabrica() as sessao:
        usuario = await sessao.scalar(select(Usuario).where(Usuario.email == "reprova@exemplo.com"))
    conversa_id, cadeia_id = await _cadeia_para_verificar(fabrica, usuario.id)

    # 1ª reprovação
    ctx = _ctx_com_modelo(fabrica, redis, lambda papel: [_modelo_do_veredito(False)])
    await verificar_cadeia(ctx, str(cadeia_id))
    async with fabrica() as sessao:
        cadeia = await sessao.get(Cadeia, cadeia_id)
        assert cadeia.status == StatusCadeia.EXECUTANDO and cadeia.rodada == 1
        etapas = (
            await sessao.scalars(
                select(Etapa)
                .where(Etapa.cadeia_id == cadeia_id)
                .order_by(Etapa.ordem, Etapa.tentativa)
            )
        ).all()
        resumo = [(e.ordem, e.tentativa, e.nivel, e.status) for e in etapas]
        assert resumo == [
            (1, 1, "N2", StatusEtapa.CONCLUIDA),
            (1, 2, "N3", StatusEtapa.PENDENTE),
            (2, 1, "N2", StatusEtapa.FALHOU),
            (2, 2, "N2", StatusEtapa.PENDENTE),
        ], resumo

    # a tentativa 2 do trabalho termina; 2ª reprovação -> falhou
    async with fabrica() as sessao:
        await sessao.execute(
            text(
                "update etapas set status = 'concluida' "
                "where cadeia_id = :c and ordem = 1 and tentativa = 2"
            ),
            {"c": cadeia_id},
        )
        await sessao.commit()
    ctx = _ctx_com_modelo(fabrica, redis, lambda papel: [_modelo_do_veredito(False)])
    await verificar_cadeia(ctx, str(cadeia_id))
    async with fabrica() as sessao:
        cadeia = await sessao.get(Cadeia, cadeia_id)
        assert cadeia.status == StatusCadeia.FALHOU and cadeia.rodada == 2
    eventos = [
        (c["event"], json.loads(c["data"]))
        for _, c in await redis.xrange(canal_conversa(conversa_id))
    ]
    status_da_cadeia = [d["status"] for n, d in eventos if n == "cadeia.atualizada"]
    assert status_da_cadeia[-1] == "falhou"

    # Verificador que quebra: etapa e cadeia `falhou`, nunca presas em `verificando`
    _, cadeia2 = await _cadeia_para_verificar(fabrica, usuario.id)

    def modelo_quebrado(papel):
        raise RuntimeError("provedor caiu")

    ctx = _ctx_com_modelo(fabrica, redis, modelo_quebrado)
    await verificar_cadeia(ctx, str(cadeia2))
    async with fabrica() as sessao:
        assert (await sessao.get(Cadeia, cadeia2)).status == StatusCadeia.FALHOU
        verificador = await sessao.scalar(
            select(Etapa).where(Etapa.cadeia_id == cadeia2, Etapa.especialista == "verificador")
        )
        assert verificador.status == StatusEtapa.FALHOU and "provedor caiu" in verificador.erro


async def test_ajustes_simultaneos_nao_repetem_a_versao(
    ambiente_fase_b: tuple[Any, async_sessionmaker, Redis],
) -> None:
    """Achado 10: dois `ajustar` ao mesmo tempo geram v2 e v3, nunca duas v2."""
    from workers.cadeia import ajustar

    cliente, fabrica, redis = ambiente_fase_b
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()
    await entrar(cliente, fabrica, "ajustes@exemplo.com")
    async with fabrica() as sessao:
        usuario = await sessao.scalar(select(Usuario).where(Usuario.email == "ajustes@exemplo.com"))
    conversa_id, cadeia_id = await _cadeia_para_verificar(fabrica, usuario.id)
    async with fabrica() as sessao:
        await sessao.execute(
            text("update etapas set status = 'concluida' where cadeia_id = :c"), {"c": cadeia_id}
        )
        await sessao.execute(
            text("update cadeias set status = 'concluida' where id = :c"), {"c": cadeia_id}
        )
        await sessao.commit()
    ctx = {"sessoes": fabrica, "redis_eventos": redis}
    await asyncio.gather(
        ajustar(ctx, str(conversa_id), "mais descontraído"),
        ajustar(ctx, str(conversa_id), "mais curto"),
    )
    async with fabrica() as sessao:
        versoes = sorted(
            (
                await sessao.scalars(select(Cadeia.versao).where(Cadeia.conversa_id == conversa_id))
            ).all()
        )
    assert versoes == [1, 2, 3], versoes


async def test_disparar_especialista_cria_o_agente_da_etapa(
    ambiente_fase_b: tuple[Any, async_sessionmaker, Redis],
) -> None:
    """Achado 1: a etapa criada pela ferramenta tem agente (antes: AssertionError no worker)."""
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.disparar_especialista import DispararEspecialista, disparar_especialista

    cliente, fabrica, _ = ambiente_fase_b
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()
    await entrar(cliente, fabrica, "dispara@exemplo.com")
    async with fabrica() as sessao:
        usuario = await sessao.scalar(select(Usuario).where(Usuario.email == "dispara@exemplo.com"))
        sora = await sessao.scalar(
            select(Agente).where(Agente.usuario_id == usuario.id, Agente.tipo == TipoAgente.SORA)
        )
    conversa_id, cadeia_id, _ = await _cadeia_e_etapa(fabrica, usuario.id, StatusCadeia.EXECUTANDO)
    contexto = ContextoFerramenta(
        usuario_id=usuario.id, agente_id=sora.id, conversa_id=conversa_id, cadeia_id=cadeia_id
    )
    etapa_id = await disparar_especialista(
        DispararEspecialista(papel="redator", tarefa="Escreva a legenda."), contexto
    )
    async with fabrica() as sessao:
        etapa = await sessao.get(Etapa, UUID(etapa_id))
        assert etapa.agente_id is not None
        agente = await sessao.get(Agente, etapa.agente_id)
        assert agente.papel == "redator" and agente.usuario_id == usuario.id
        assert agente.cadeia_id == cadeia_id
    # repetir o mesmo disparo não duplica nem o agente nem a etapa
    de_novo = await disparar_especialista(
        DispararEspecialista(papel="redator", tarefa="Escreva a legenda."), contexto
    )
    assert de_novo == etapa_id


async def test_designer_so_entra_com_modelo_de_imagem(ambiente_http: AmbienteHttp) -> None:
    """Achado 12: com modelo de imagem conectado o Designer deixa de ser rejeitado."""
    from workers.cadeia import _tem_modelo_de_imagem

    amb = ambiente_http
    async with httpx.AsyncClient(base_url=amb.url_api, timeout=60) as cliente:
        _, usuario_id = await usuario_com_modelo_http(amb, cliente, "designer@exemplo.com")
        async with amb.fabrica() as sessao:
            assert await _tem_modelo_de_imagem(sessao, usuario_id) is False
            provedor = await sessao.scalar(
                select(Provedor).where(Provedor.usuario_id == usuario_id)
            )
            sessao.add(
                ModeloDisponivel(
                    provedor_id=provedor.id,
                    modelo="openai/gpt-image-1",
                    nivel="N2",
                    capacidades=["imagem"],
                    contexto=4_000,
                    velocidade_tps=10,
                )
            )
            await sessao.commit()
            assert await _tem_modelo_de_imagem(sessao, usuario_id) is True


async def test_portas_do_worker_cancelamento_orcamento_e_saida_grande(
    ambiente_fase_b: tuple[Any, async_sessionmaker, Redis],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Achado 5: as portas que ligam os middlewares existem e funcionam de verdade."""
    from app.orquestrador.cadeia import chave_de_cancelamento
    from workers.portas import construir_dependencias

    monkeypatch.setenv("PASTA_ARQUIVOS", str(tmp_path))
    obter_configuracao.cache_clear()

    cliente, fabrica, redis = ambiente_fase_b
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()
    await entrar(cliente, fabrica, "portas@exemplo.com")
    async with fabrica() as sessao:
        usuario = await sessao.scalar(select(Usuario).where(Usuario.email == "portas@exemplo.com"))
    conversa_id, cadeia_id, _ = await _cadeia_e_etapa(fabrica, usuario.id, StatusCadeia.EXECUTANDO)
    deps = construir_dependencias(
        {"redis_eventos": redis},
        usuario_id=usuario.id,
        conversa_id=conversa_id,
        cadeia_id=cadeia_id,
        orcamento_tokens=1_000,
    )
    assert all(
        porta is not None
        for porta in (
            deps.esta_cancelada,
            deps.reservar_tokens,
            deps.corrigir_tokens,
            deps.iniciar_passo,
            deps.finalizar_passo,
            deps.salvar_saida,
            deps.ler_mensagens_pendentes,
        )
    )
    assert deps.orcamento_tokens == 1_000

    # orçamento: reserva dentro do teto passa, a que estoura é recusada e não fica reservada
    assert await deps.reservar_tokens(cadeia_id, 600, 1_000) is True
    assert await deps.reservar_tokens(cadeia_id, 600, 1_000) is False
    await deps.corrigir_tokens(cadeia_id, 600, 200)  # o uso real foi menor: devolve a sobra
    assert await deps.reservar_tokens(cadeia_id, 700, 1_000) is True
    async with fabrica() as sessao:
        assert (await sessao.get(Cadeia, cadeia_id)).tokens_usados == 200

    # cancelamento: a chave do Redis (gravada pela API) ou o status no banco
    assert await deps.esta_cancelada(cadeia_id) is False
    await redis.set(chave_de_cancelamento(cadeia_id), "1")
    assert await deps.esta_cancelada(cadeia_id) is True
    await redis.delete(chave_de_cancelamento(cadeia_id))
    async with fabrica() as sessao:
        await sessao.execute(
            text("update cadeias set status = 'cancelada' where id = :c"), {"c": cadeia_id}
        )
        await sessao.commit()
    assert await deps.esta_cancelada(cadeia_id) is True

    # saída grande: vai para arquivo da cadeia e devolve só o nome
    nome = await deps.salvar_saida(cadeia_id, "x" * 30_000)
    assert nome.startswith("saida-") and nome.endswith(".txt")


async def test_resposta_acorda_a_etapa_que_perguntou_e_nao_a_primeira(
    ambiente_fase_b: tuple[Any, async_sessionmaker, Redis],
    servicos_fase_b: tuple[str, str],
) -> None:
    """Achado 8: duas etapas esperando o usuário; a resposta da 2ª pergunta acorda a 2ª etapa."""
    cliente, fabrica, _ = ambiente_fase_b
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()
    auth = await entrar(cliente, fabrica, "paralelas@exemplo.com")
    async with fabrica() as sessao:
        usuario = await sessao.scalar(
            select(Usuario).where(Usuario.email == "paralelas@exemplo.com")
        )
    conversa_id, cadeia_id, etapa1 = await _cadeia_e_etapa(
        fabrica, usuario.id, StatusCadeia.AGUARDANDO_USUARIO
    )
    async with fabrica() as sessao:
        primeira = await sessao.get(Etapa, etapa1)
        segunda = Etapa(
            cadeia_id=cadeia_id,
            ordem=2,
            depende_de=[],
            especialista="redator",
            agente_id=primeira.agente_id,
            titulo="Escrever",
            nivel="N2",
            tarefa="Escreva.",
            status=StatusEtapa.AGUARDANDO_USUARIO,
        )
        primeira.status = StatusEtapa.AGUARDANDO_USUARIO
        sessao.add(segunda)
        perguntas = [
            Pergunta(
                conversa_id=conversa_id,
                cadeia_id=cadeia_id,
                texto=t,
                opcoes=[],
                resposta_livre=True,
            )
            for t in ("Primeira?", "Segunda?")
        ]
        sessao.add_all(perguntas)
        await sessao.flush()
        primeira.saida = {"pergunta_id": str(perguntas[0].id)}
        segunda.saida = {"pergunta_id": str(perguntas[1].id)}
        await sessao.commit()
        id_segunda, id_pergunta2 = segunda.id, perguntas[1].id

    resposta = await cliente.post(
        f"/v1/perguntas/{id_pergunta2}/responder", headers=auth, json={"valor": "sim"}
    )
    assert resposta.status_code == 204, resposta.text
    fila = await create_pool(RedisSettings.from_dsn(servicos_fase_b[1]))
    try:
        jobs = await fila.queued_jobs()
    finally:
        await fila.aclose()
    retomadas = [j for j in jobs if j.function == "executar_etapa"]
    assert [j.args[0] for j in retomadas] == [str(id_segunda)]


def test_worker_sobe_no_windows_sem_sigusr1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vitral: `python -m workers` prepara o loop selector e o SIGUSR1 que o ARQ usa ao fechar."""
    from workers import __main__ as entrada

    if sys.platform != "win32":
        pytest.skip("ajustes só do Windows")
    monkeypatch.delattr(signal, "SIGUSR1", raising=False)
    entrada.preparar_windows()
    assert hasattr(signal, "SIGUSR1")
    assert isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy)
