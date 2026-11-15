"""Etapa 6, Âncora-4, com PostgreSQL e Redis reais: visão e imagem na resposta (10), memória e
rotinas por bot (14) e busca nas mensagens (17)."""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import insert, select, update

from app.eventos.streams import canal_usuario
from app.ferramentas.base import ContextoFerramenta
from app.modelos.enumeracoes import AutorMensagem
from app.modelos.tabelas import (
    Agente,
    Anexo,
    Conversa,
    Mensagem,
    MensagemCanalTabela,
    Usuario,
)
from tests.integracao.relogio_base import Mundo, mundo  # noqa: F401
from tests.integracao.relogio_base import servicos_relogio as _servicos_testcontainers
from tests.integracao.test_fase_b_pronto import entrar

pytestmark = pytest.mark.integracao

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="module")
def servicos_relogio():
    """Usa os serviços da etapa 5 quando informados; senão cria contêineres descartáveis."""
    if os.environ.get("SORA_TESTE_PG") and os.environ.get("SORA_TESTE_REDIS"):
        yield os.environ["SORA_TESTE_PG"], os.environ["SORA_TESTE_REDIS"]
        return
    yield from _servicos_testcontainers.__wrapped__()


@pytest.fixture(autouse=True)
def pasta(tmp_path, monkeypatch):
    """Volume de anexos descartável (definido antes de ``mundo`` ler a configuração)."""
    monkeypatch.setenv("PASTA_ARQUIVOS", str(tmp_path / "arquivos"))
    yield tmp_path / "arquivos"


async def _usuario_id(mundo_: Mundo, email: str) -> UUID:
    async with mundo_.fabrica() as sessao:
        return await sessao.scalar(select(Usuario.id).where(Usuario.email == email))


async def _bot(cliente: httpx.AsyncClient, auth: dict, nome: str) -> dict:
    resposta = await cliente.post(
        "/v1/agentes",
        headers=auth,
        json={"nome": nome, "funcao": "Ajuda", "papel": "pesquisador", "cor": "#56A8FF"},
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


async def _conversa(mundo_: Mundo, usuario_id: UUID, agente_id: UUID) -> UUID:
    async with mundo_.fabrica() as sessao:
        conversa = Conversa(usuario_id=usuario_id, agente_id=agente_id, titulo="Papo")
        sessao.add(conversa)
        await sessao.commit()
        return conversa.id


# ------------------------------------------------------------------ item 14: memória


async def test_memoria_editar_desfazer_e_isolamento(mundo: Mundo, pasta) -> None:  # noqa: F811
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        a = await entrar(cliente, mundo.fabrica, f"mem-a-{uuid4()}@exemplo.com")
        b = await entrar(cliente, mundo.fabrica, f"mem-b-{uuid4()}@exemplo.com")
        bot = await _bot(cliente, a, "Lume")

        criada = await cliente.post(
            "/v1/memorias", headers=a, json={"conteudo": "Prefere café", "agente_id": bot["id"]}
        )
        assert criada.status_code == 201, criada.text
        memoria_id = criada.json()["id"]
        outra = await cliente.post(
            "/v1/memorias", headers=a, json={"conteudo": "Trabalha à noite", "agente_id": bot["id"]}
        )
        assert outra.status_code == 201

        editada = await cliente.patch(
            f"/v1/memorias/{memoria_id}", headers=a, json={"conteudo": "  Prefere café   coado "}
        )
        assert editada.status_code == 200, editada.text
        assert editada.json()["conteudo"] == "Prefere café coado"
        assert editada.json()["id"] == memoria_id and editada.json()["origem"] == "explicita"
        textos = [m["conteudo"] for m in (await cliente.get("/v1/memorias", headers=a)).json()]
        assert "Prefere café coado" in textos and "Prefere café" not in textos

        repetida = await cliente.patch(
            f"/v1/memorias/{memoria_id}", headers=a, json={"conteudo": "trabalha À NOITE"}
        )
        assert repetida.status_code == 422 and "Já existe" in repetida.json()["detail"]
        segredo = await cliente.patch(
            f"/v1/memorias/{memoria_id}",
            headers=a,
            json={"conteudo": "token sk-abcdefghijklmnopqrstuvwxyz012345"},
        )
        assert segredo.status_code == 422
        assert (
            await cliente.patch(f"/v1/memorias/{memoria_id}", headers=a, json={"conteudo": ""})
        ).status_code == 422

        # Outro usuário: some para ele (404), tanto editar quanto apagar.
        assert (
            await cliente.patch(f"/v1/memorias/{memoria_id}", headers=b, json={"conteudo": "x1"})
        ).status_code == 404
        assert (await cliente.delete(f"/v1/memorias/{memoria_id}", headers=b)).status_code == 404
        textos = [m["conteudo"] for m in (await cliente.get("/v1/memorias", headers=a)).json()]
        assert "Prefere café coado" in textos  # a de A continua intacta

        # Desfazer (o chip "Guardei isto"): o DELETE; depois disso editar dá 404.
        assert (await cliente.delete(f"/v1/memorias/{memoria_id}", headers=a)).status_code == 204
        assert (
            await cliente.patch(f"/v1/memorias/{memoria_id}", headers=a, json={"conteudo": "volta"})
        ).status_code == 404
        assert (await cliente.get("/v1/memorias", headers=b)).json() == []


async def test_lembrar_emite_memoria_criada_so_para_memoria_nova(mundo: Mundo, pasta) -> None:  # noqa: F811
    from app.ferramentas.pecas import lembrar
    from app.memoria.servico import Lembrar

    email = f"mem-evento-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        bot = await _bot(cliente, auth, "Nexo")
        usuario_id = await _usuario_id(mundo, email)
        conversa_id = await _conversa(mundo, usuario_id, UUID(bot["id"]))
        contexto = ContextoFerramenta(
            usuario_id=usuario_id, agente_id=UUID(bot["id"]), conversa_id=conversa_id
        )

        await lembrar(Lembrar(conteudo="O usuário prefere reuniões de manhã"), contexto)
        await lembrar(Lembrar(conteudo="o usuário prefere reuniões de manhã"), contexto)  # repetida
        longa = "Detalhe " * 60
        await lembrar(Lembrar(conteudo=longa.strip()[:490]), contexto)

        redis = Redis.from_url(mundo.url_redis)
        try:
            entradas = await redis.xrange(canal_usuario(usuario_id))
        finally:
            await redis.aclose()
        eventos = [
            json.loads(campos[b"data"])
            for _, campos in entradas
            if campos[b"event"] == b"memoria.criada"
        ]
        assert len(eventos) == 2  # a repetida não gera chip
        primeiro, segundo = eventos
        assert primeiro["texto"] == "O usuário prefere reuniões de manhã"
        assert primeiro["agente_id"] == bot["id"] and primeiro["conversa_id"] == str(conversa_id)
        assert len(segundo["texto"]) <= 160 and segundo["texto"].endswith("…")

        # Desfazer pelo id do evento.
        assert (
            await cliente.delete(f"/v1/memorias/{primeiro['memoria_id']}", headers=auth)
        ).status_code == 204


# ------------------------------------------------------------------ item 14: rotinas por bot


async def test_rotinas_por_bot_pausar_retomar_executar_e_isolamento(
    mundo: Mundo,  # noqa: F811
    pasta,
) -> None:
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        a = await entrar(cliente, mundo.fabrica, f"rot-a-{uuid4()}@exemplo.com")
        b = await entrar(cliente, mundo.fabrica, f"rot-b-{uuid4()}@exemplo.com")
        bot1, bot2 = await _bot(cliente, a, "Lume"), await _bot(cliente, a, "Nexo")

        async def criar(bot: dict, titulo: str) -> dict:
            resposta = await cliente.post(
                "/v1/rotinas",
                headers=a,
                json={
                    "agente_id": bot["id"],
                    "titulo": titulo,
                    "pedido": "Resumir as novidades",
                    "cron": "0 9 * * 1-5",
                },
            )
            assert resposta.status_code == 201, resposta.text
            return resposta.json()

        r1, r2 = await criar(bot1, "Manhã"), await criar(bot2, "Tarde")
        assert r1["proxima_execucao"] and r1["ativa"] is True

        so_do_bot1 = (
            await cliente.get("/v1/rotinas", headers=a, params={"agente_id": bot1["id"]})
        ).json()
        assert [r["id"] for r in so_do_bot1] == [r1["id"]]
        todas = (await cliente.get("/v1/rotinas", headers=a)).json()
        assert {r["id"] for r in todas} == {r1["id"], r2["id"]}

        pausada = await cliente.patch(f"/v1/rotinas/{r1['id']}", headers=a, json={"ativa": False})
        assert pausada.status_code == 200 and pausada.json()["ativa"] is False
        retomada = await cliente.patch(f"/v1/rotinas/{r1['id']}", headers=a, json={"ativa": True})
        assert retomada.json()["ativa"] is True and retomada.json()["proxima_execucao"]

        agora = await cliente.post(f"/v1/rotinas/{r1['id']}/executar", headers=a)
        assert agora.status_code == 202
        execucoes = await cliente.get(
            f"/v1/rotinas/{r1['id']}/execucoes", headers=a, params={"limite": 5}
        )
        assert execucoes.status_code == 200
        assert [e["id"] for e in execucoes.json()] == [agora.json()["execucao_id"]]

        # Outro usuário não vê, não pausa, não executa, não lê execuções, nem filtra por bot alheio.
        assert (await cliente.get("/v1/rotinas", headers=b)).json() == []
        assert (
            await cliente.get("/v1/rotinas", headers=b, params={"agente_id": bot1["id"]})
        ).json() == []
        assert (
            await cliente.patch(f"/v1/rotinas/{r1['id']}", headers=b, json={"ativa": False})
        ).status_code == 404
        assert (
            await cliente.post(f"/v1/rotinas/{r1['id']}/executar", headers=b)
        ).status_code == 404
        assert (
            await cliente.get(f"/v1/rotinas/{r1['id']}/execucoes", headers=b)
        ).status_code == 404
        criada_no_bot_alheio = await cliente.post(
            "/v1/rotinas",
            headers=b,
            json={
                "agente_id": bot1["id"],
                "titulo": "Invasão",
                "pedido": "Faça algo",
                "cron": "0 9 * * *",
            },
        )
        assert criada_no_bot_alheio.status_code == 404


# ------------------------------------------------------------------ item 17: busca


async def test_busca_acha_em_conversas_e_grupos_e_nunca_de_outro_usuario(
    mundo: Mundo,  # noqa: F811
    pasta,
) -> None:
    email_a, email_b = f"busca-a-{uuid4()}@exemplo.com", f"busca-b-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        a = await entrar(cliente, mundo.fabrica, email_a)
        b = await entrar(cliente, mundo.fabrica, email_b)
        usuario_a, usuario_b = await _usuario_id(mundo, email_a), await _usuario_id(mundo, email_b)
        sora_a = (await cliente.get("/v1/agentes/sora", headers=a)).json()
        sora_b = (await cliente.get("/v1/agentes/sora", headers=b)).json()
        lume, nexo = await _bot(cliente, a, "Lume"), await _bot(cliente, a, "Nexo")
        bot_b = await _bot(cliente, b, "Lume")
        grupo = (
            await cliente.post(
                "/v1/grupos",
                headers=a,
                json={"nome": "Lançamento", "membros": [lume["id"], nexo["id"]]},
            )
        ).json()

        agora = datetime.now(UTC)
        conversa_sora = await _conversa(mundo, usuario_a, UUID(sora_a["id"]))
        conversa_lume = await _conversa(mundo, usuario_a, UUID(lume["id"]))
        conversa_b = await _conversa(mundo, usuario_b, UUID(sora_b["id"]))
        conversa_bot_b = await _conversa(mundo, usuario_b, UUID(bot_b["id"]))
        async with mundo.fabrica() as sessao:
            m_sora = Mensagem(
                conversa_id=conversa_sora,
                autor=AutorMensagem.USUARIO,
                conteudo="Preciso do ORÇAMENTO da campanha de inverno",
                criada_em=agora - timedelta(days=3),
            )
            m_lume = Mensagem(
                conversa_id=conversa_lume,
                autor=AutorMensagem.AGENTE,
                agente_id=UUID(lume["id"]),
                conteudo="Montei o orcamento: três linhas de custo.",
                criada_em=agora - timedelta(days=1),
            )
            m_oculta = Mensagem(
                conversa_id=conversa_lume,
                autor=AutorMensagem.AGENTE,
                agente_id=UUID(lume["id"]),
                conteudo="orçamento (mensagem interna, invisível)",
                visivel=False,
                criada_em=agora,
            )
            # Mensagens do outro usuário com as mesmas palavras: jamais aparecem para A.
            m_b1 = Mensagem(
                conversa_id=conversa_b,
                autor=AutorMensagem.USUARIO,
                conteudo="Segredo do orçamento da campanha do B",
                criada_em=agora,
            )
            m_b2 = Mensagem(
                conversa_id=conversa_bot_b,
                autor=AutorMensagem.USUARIO,
                conteudo="orçamento orçamento orçamento",
                criada_em=agora,
            )
            sessao.add_all([m_sora, m_lume, m_oculta, m_b1, m_b2])
            sessao.add(
                MensagemCanalTabela(
                    canal_id=UUID(grupo["id"]),
                    seq=1,
                    autor="usuario",
                    texto="@todos fechem o Orçamento até sexta",
                    tipo="mensagem",
                    criada_em=agora - timedelta(hours=2),
                )
            )
            sessao.add(
                MensagemCanalTabela(
                    canal_id=UUID(grupo["id"]),
                    seq=2,
                    autor="sistema",
                    texto="Lume começou a tarefa de orçamento",
                    tipo="atividade",
                    criada_em=agora - timedelta(hours=1),
                )
            )
            await sessao.commit()

        resposta = await cliente.get("/v1/busca", headers=a, params={"q": "orcamento"})
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["consulta"] == "orcamento"
        resultados = corpo["resultados"]
        # Do mais novo ao mais antigo; sem a oculta, sem a atividade, sem nada do usuário B.
        assert [r["tipo"] for r in resultados] == ["grupo", "conversa", "conversa"]
        grupo_r, lume_r, sora_r = resultados
        assert grupo_r["grupo_id"] == grupo["id"] and grupo_r["titulo"] == "Lançamento"
        assert grupo_r["seq"] == 1 and grupo_r["autor"] == "usuario"
        assert [grupo_r["trecho"][i:f] for i, f in grupo_r["destaques"]] == ["Orçamento"]
        assert lume_r["conversa_id"] == str(conversa_lume) and lume_r["titulo"] == "Lume"
        assert lume_r["autor"] == "agente" and lume_r["autor_nome"] == "Lume"
        assert lume_r["agente_id"] == lume["id"] and lume_r["mensagem_id"] == str(m_lume.id)
        assert [lume_r["trecho"][i:f] for i, f in lume_r["destaques"]] == ["orcamento"]
        assert sora_r["titulo"] == "Sora" and sora_r["autor_nome"] == "Você"
        assert sora_r["mensagem_id"] == str(m_sora.id)
        assert [sora_r["trecho"][i:f] for i, f in sora_r["destaques"]] == ["ORÇAMENTO"]
        ids_do_b = {str(m_b1.id), str(m_b2.id), str(m_oculta.id)}
        assert not ids_do_b & {r["mensagem_id"] for r in resultados}

        # Várias palavras: todas têm de aparecer na mesma mensagem.
        duas = (
            await cliente.get("/v1/busca", headers=a, params={"q": "campanha ORÇAMENTO"})
        ).json()
        assert [r["mensagem_id"] for r in duas["resultados"]] == [str(m_sora.id)]
        nenhuma = (await cliente.get("/v1/busca", headers=a, params={"q": "campanha sexta"})).json()
        assert nenhuma["resultados"] == []

        # O B só enxerga o que é dele.
        do_b = (await cliente.get("/v1/busca", headers=b, params={"q": "orçamento"})).json()
        assert {r["mensagem_id"] for r in do_b["resultados"]} == {str(m_b1.id), str(m_b2.id)}

        # Termo curto demais, caracteres de LIKE e limite.
        assert (await cliente.get("/v1/busca", headers=a, params={"q": "o"})).json()[
            "resultados"
        ] == []
        assert (await cliente.get("/v1/busca", headers=a, params={"q": "100%"})).json()[
            "resultados"
        ] == []
        assert (await cliente.get("/v1/busca", headers=a, params={"q": "__"})).json()[
            "resultados"
        ] == []
        um = await cliente.get("/v1/busca", headers=a, params={"q": "orcamento", "limite": 1})
        assert len(um.json()["resultados"]) == 1
        assert (await cliente.get("/v1/busca", headers=a)).status_code == 422
        assert (await cliente.get("/v1/busca", params={"q": "orcamento"})).status_code == 401

        # Bot apagado sai da busca.
        assert (await cliente.delete(f"/v1/agentes/{lume['id']}", headers=a)).status_code in (
            200,
            204,
        )
        depois = (await cliente.get("/v1/busca", headers=a, params={"q": "orcamento"})).json()
        assert str(m_lume.id) not in {r["mensagem_id"] for r in depois["resultados"]}


async def test_busca_com_5000_mensagens_responde_em_menos_de_300_ms(
    mundo: Mundo,  # noqa: F811
    pasta,
) -> None:
    email = f"busca-perf-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        outro = await entrar(cliente, mundo.fabrica, f"busca-perf-b-{uuid4()}@exemplo.com")
        usuario_id = await _usuario_id(mundo, email)
        sora = (await cliente.get("/v1/agentes/sora", headers=auth)).json()
        bots = [await _bot(cliente, auth, f"Bot{n}") for n in range(2)]
        grupo = (
            await cliente.post(
                "/v1/grupos",
                headers=auth,
                json={"nome": "Grande", "membros": [bot["id"] for bot in bots]},
            )
        ).json()
        conversas = [
            await _conversa(mundo, usuario_id, UUID(agente))
            for agente in (sora["id"], bots[0]["id"], bots[1]["id"])
        ]
        base = datetime.now(UTC) - timedelta(days=30)
        palavras = (
            "pauta reunião cliente contrato prazo entrega revisão proposta ajuste ideia".split()
        )
        linhas = []
        for n in range(4_500):
            linhas.append(
                {
                    "id": uuid4(),
                    "conversa_id": conversas[n % 3],
                    "autor": AutorMensagem.USUARIO if n % 2 else AutorMensagem.SORA,
                    "conteudo": f"{palavras[n % 10]} {palavras[(n * 7) % 10]} número {n} "
                    + "texto de enchimento " * 6,
                    "visivel": True,
                    "criada_em": base + timedelta(minutes=n),
                }
            )
        linhas[1234]["conteudo"] = "A palavra xilofone aparece só aqui"
        async with mundo.fabrica() as sessao:
            await sessao.execute(insert(Mensagem), linhas)
            await sessao.execute(
                insert(MensagemCanalTabela),
                [
                    {
                        "id": uuid4(),
                        "canal_id": UUID(grupo["id"]),
                        "seq": n + 1,
                        "autor": "usuario",
                        "tipo": "mensagem",
                        "texto": f"{palavras[n % 10]} tarefa do grupo {n} " + "conversa longa " * 8,
                        "anexos": [],
                        "criada_em": base + timedelta(minutes=n),
                    }
                    for n in range(500)
                ],
            )
            await sessao.commit()
            total = len(linhas) + 500
        assert total == 5_000

        async def medir(q: str) -> tuple[float, dict]:
            inicio = time.perf_counter()
            resposta = await cliente.get("/v1/busca", headers=auth, params={"q": q})
            duracao = time.perf_counter() - inicio
            assert resposta.status_code == 200, resposta.text
            return duracao, resposta.json()

        await medir("aquecimento")
        inicio = time.perf_counter()
        assert (await cliente.get("/v1/memorias", headers=auth)).status_code == 200
        base_http = time.perf_counter() - inicio
        raro_tempo, raro = await medir("XILOFONE")
        assert [r["autor"] for r in raro["resultados"]] == ["sora" if 1234 % 2 == 0 else "usuario"]
        comum_tempo, comum = await medir("contrato reuniao")
        assert len(comum["resultados"]) == 20  # limite padrão
        sem_acento_tempo, _ = await medir("reuniao")
        melhor = {
            "raro": min([raro_tempo] + [(await medir("xilofone"))[0] for _ in range(4)]),
            "comum": min([comum_tempo] + [(await medir("contrato reuniao"))[0] for _ in range(4)]),
            "sem acento": min([sem_acento_tempo] + [(await medir("reuniao"))[0] for _ in range(4)]),
        }
        print(
            "busca com 5.000 mensagens (melhor de 5, ms):",
            {k: round(v * 1000) for k, v in melhor.items()},
        )
        print("rota simples (referência, ms):", round(base_http * 1000))
        assert all(v < 0.3 for v in melhor.values()), melhor

        # O outro usuário (sem mensagens) não vê nada disso.
        assert (await cliente.get("/v1/busca", headers=outro, params={"q": "xilofone"})).json()[
            "resultados"
        ] == []


# ------------------------------------------------------------------ item 10: imagem na resposta


@pytest.fixture
def seletor_de_imagem(monkeypatch):
    """O usuário "tem" um modelo de imagem (a geração em si é o modelo falso do ambiente)."""
    import app.ferramentas.gerar_imagem as modulo

    provedor = SimpleNamespace(id=uuid4())

    async def contexto_do_usuario(sessao, usuario_id, **_):
        return SimpleNamespace()

    async def config_do_provedor(sessao, usuario_id, provedor_id):
        return SimpleNamespace(provedor_id=provedor_id)

    async def gravar_chamada(*_args, **_kwargs):
        return None

    monkeypatch.setattr(modulo, "contexto_do_usuario", contexto_do_usuario)
    monkeypatch.setattr(modulo, "config_do_provedor", config_do_provedor)
    monkeypatch.setattr(modulo, "gravar_chamada", gravar_chamada)
    monkeypatch.setattr(
        modulo,
        "escolher_modelos",
        lambda *_a, **_k: SimpleNamespace(
            modelos=[SimpleNamespace(modelo="falso/imagem", provedor=provedor)]
        ),
    )


async def test_imagem_gerada_sai_como_anexo_da_mensagem_do_bot(
    mundo: Mundo,  # noqa: F811
    pasta,
    seletor_de_imagem,
) -> None:
    from app.ferramentas.falar import Falar, falar
    from app.ferramentas.gerar_imagem import GerarImagem, gerar_imagem

    email = f"img-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        intruso = await entrar(cliente, mundo.fabrica, f"img-b-{uuid4()}@exemplo.com")
        bot = await _bot(cliente, auth, "Lume")
        usuario_id = await _usuario_id(mundo, email)
        conversa_id = await _conversa(mundo, usuario_id, UUID(bot["id"]))
        contexto = ContextoFerramenta(
            usuario_id=usuario_id, agente_id=UUID(bot["id"]), conversa_id=conversa_id
        )

        retorno = await gerar_imagem(
            GerarImagem(descricao="um gato astronauta", quantidade=2), contexto
        )
        assert "próxima mensagem" in retorno

        # O modelo esqueceu de passar ``anexos``: a imagem vai junto mesmo assim.
        await falar(Falar(texto="Pronto, aqui estão as imagens."), contexto)
        # E só uma vez: a mensagem seguinte não repete.
        await falar(Falar(texto="Quer outra versão?"), contexto)

        mensagens = (
            await cliente.get(f"/v1/conversas/{conversa_id}/mensagens", headers=auth)
        ).json()
        bot_msgs = [m for m in mensagens if m["autor"] == "agente"]
        assert [m["conteudo"] for m in bot_msgs] == [
            "Pronto, aqui estão as imagens.",
            "Quer outra versão?",
        ]
        assert len(bot_msgs[0]["anexos"]) == 2 and bot_msgs[1]["anexos"] == []

        for anexo_id in bot_msgs[0]["anexos"]:
            anexo_id = anexo_id["id"] if isinstance(anexo_id, dict) else anexo_id
            baixado = await cliente.get(f"/v1/anexos/{anexo_id}", headers=auth)
            assert baixado.status_code == 200
            assert baixado.headers["content-type"].startswith("image/")
            assert baixado.content[:4] == b"\x89PNG"
            # Controle de dono: outro usuário não baixa.
            assert (await cliente.get(f"/v1/anexos/{anexo_id}", headers=intruso)).status_code == 404

        # Anexo explícito do modelo continua valendo e não duplica com o pendente.
        await gerar_imagem(GerarImagem(descricao="outra"), contexto)
        async with mundo.fabrica() as sessao:
            ultimo = await sessao.scalar(
                select(Anexo.id)
                .where(Anexo.usuario_id == usuario_id, Anexo.origem == "especialista")
                .order_by(Anexo.criado_em.desc())
            )
        await falar(Falar(texto="Mais uma.", anexos=[ultimo]), contexto)
        mensagens = (
            await cliente.get(f"/v1/conversas/{conversa_id}/mensagens", headers=auth)
        ).json()
        assert len([m for m in mensagens if m["autor"] == "agente"][-1]["anexos"]) == 1


async def test_arquivo_escrito_pelo_bot_e_imagem_no_grupo_chegam_no_resultado(
    mundo: Mundo,  # noqa: F811
    pasta,
    seletor_de_imagem,
) -> None:
    from app.canais_equipe.execucao import canal_resultado
    from app.canais_equipe.ferramentas import CanalResultado
    from app.ferramentas.escrever_arquivo import EscreverArquivo, escrever_arquivo
    from app.ferramentas.gerar_imagem import GerarImagem, gerar_imagem
    from app.modelos.tabelas import TarefaCanalTabela

    email = f"grupo-img-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        usuario_id = await _usuario_id(mundo, email)
        lume, nexo = await _bot(cliente, auth, "Lume"), await _bot(cliente, auth, "Nexo")
        grupo = (
            await cliente.post(
                "/v1/grupos",
                headers=auth,
                json={"nome": "Arte", "membros": [lume["id"], nexo["id"]]},
            )
        ).json()
        pedido = await cliente.post(
            f"/v1/canais-equipe/{grupo['id']}/mensagens",
            headers=auth,
            json={"texto": "Faça a arte do cartaz", "destinatario": lume["id"]},
        )
        assert pedido.status_code == 202, pedido.text
        async with mundo.fabrica() as sessao:
            tarefa = await sessao.scalar(
                select(TarefaCanalTabela).where(
                    TarefaCanalTabela.canal_id == UUID(grupo["id"]),
                    TarefaCanalTabela.dono_id == UUID(lume["id"]),
                )
            )
        assert tarefa is not None
        async with mundo.fabrica() as sessao:  # sem worker: a tarefa "está rodando" para o teste
            await sessao.execute(
                update(TarefaCanalTabela)
                .where(TarefaCanalTabela.id == tarefa.id)
                .values(status="rodando")
            )
            await sessao.commit()
        contexto = ContextoFerramenta(
            usuario_id=usuario_id,
            agente_id=UUID(lume["id"]),
            conversa_id=UUID(grupo["id"]),
            canal_id=UUID(grupo["id"]),
            tarefa_canal_id=tarefa.id,
            revisao_canal=tarefa.revisao,
        )
        await gerar_imagem(GerarImagem(descricao="cartaz"), contexto)
        await escrever_arquivo(
            EscreverArquivo(nome="legenda.txt", conteudo="Legenda do cartaz"), contexto
        )
        await canal_resultado(CanalResultado(texto="Cartaz pronto."), contexto)

        async with mundo.fabrica() as sessao:
            resultado = await sessao.scalar(
                select(MensagemCanalTabela).where(
                    MensagemCanalTabela.canal_id == UUID(grupo["id"]),
                    MensagemCanalTabela.tipo == "resultado",
                )
            )
        assert resultado is not None and len(resultado.anexos) == 2
        mensagens = (
            await cliente.get(f"/v1/canais-equipe/{grupo['id']}/mensagens", headers=auth)
        ).json()
        do_resultado = next(m for m in mensagens if m["tipo"] == "resultado")
        assert len(do_resultado["anexos"]) == 2
        tipos = set()
        for anexo_id in do_resultado["anexos"]:
            baixado = await cliente.get(f"/v1/anexos/{anexo_id}", headers=auth)
            assert baixado.status_code == 200
            tipos.add(baixado.headers["content-type"].split(";")[0])
        assert tipos == {"image/png", "text/plain"}


# ------------------------------------------------------------------ item 10: visão (worker)


async def _preparar_turno_com_anexo(
    mundo: Mundo,  # noqa: F811
    cliente: httpx.AsyncClient,
    auth: dict,
    email: str,
    pasta,
    *,
    dono_do_anexo: UUID | None = None,
    nome: str = "foto.png",
    conteudo: bytes = PNG,
) -> tuple[UUID, UUID, UUID, UUID]:
    """(usuario, bot, conversa, mensagem) com a mensagem do usuário apontando para um anexo."""
    bot = await _bot(cliente, auth, "Lume")
    usuario_id = await _usuario_id(mundo, email)
    conversa_id = await _conversa(mundo, usuario_id, UUID(bot["id"]))
    anexo_id = uuid4()
    dono = dono_do_anexo or usuario_id
    destino = pasta / str(dono) / str(anexo_id)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
    async with mundo.fabrica() as sessao:
        sessao.add(
            Anexo(
                id=anexo_id,
                usuario_id=dono,
                nome=nome,
                tipo="image/png",
                tamanho=len(conteudo),
                caminho=f"{dono}/{anexo_id}",
                origem="usuario",
            )
        )
        await sessao.flush()
        mensagem = Mensagem(
            conversa_id=conversa_id,
            autor=AutorMensagem.USUARIO,
            conteudo="O que tem nesta imagem? [grupo]",
            anexos=[str(anexo_id)],
        )
        sessao.add(mensagem)
        await sessao.commit()
        return usuario_id, UUID(bot["id"]), conversa_id, mensagem.id


async def _rodar_turno(mundo: Mundo, mensagem_id: UUID, monkeypatch) -> dict:  # noqa: F811
    import workers.conversa as conversa

    capturado: dict = {}

    async def falso(ctx, contexto, modelos, *, antes, entrada=None, resposta=None):
        capturado.update(contexto=contexto, modelos=modelos, antes=antes, entrada=entrada)

    monkeypatch.setattr(conversa, "_rodar_e_falar", falso)
    redis = Redis.from_url(mundo.url_redis)
    try:
        ctx = {"sessoes": mundo.fabrica, "redis_eventos": redis, "checkpointer": None}
        await conversa._responder_direto_sem_fila(ctx, str(mensagem_id))
    finally:
        await redis.aclose()
    return capturado


async def test_imagem_anexada_chega_ao_modelo_com_visao(
    mundo: Mundo,  # noqa: F811
    pasta,
    monkeypatch,
) -> None:
    email = f"visao-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        _, _, _, mensagem_id = await _preparar_turno_com_anexo(mundo, cliente, auth, email, pasta)
        capturado = await _rodar_turno(mundo, mensagem_id, monkeypatch)

    atual = capturado["entrada"]["messages"][-1]
    assert isinstance(atual.content, list)
    assert (
        atual.content[0]["type"] == "text" and "O que tem nesta imagem?" in atual.content[0]["text"]
    )
    assert "anexo_id:" in atual.content[0]["text"]
    imagem = atual.content[1]
    assert imagem["type"] == "image_url"
    assert base64.b64decode(imagem["image_url"]["url"].split(",", 1)[1]) == PNG


async def test_modelo_sem_visao_gera_aviso_no_chat_e_nota_para_o_bot(
    mundo: Mundo,  # noqa: F811
    pasta,
    monkeypatch,
) -> None:
    import app.agentes.visao as visao
    from app.orquestrador.modelos import modelos_do_papel

    async def sem_visao(sessao, usuario_id, papel, **kwargs):
        return await modelos_do_papel(sessao, usuario_id, papel, **kwargs), False

    monkeypatch.setattr(visao, "modelos_com_visao", sem_visao)
    email = f"sem-visao-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        _, bot_id, conversa_id, mensagem_id = await _preparar_turno_com_anexo(
            mundo, cliente, auth, email, pasta
        )
        capturado = await _rodar_turno(mundo, mensagem_id, monkeypatch)
        mensagens = (
            await cliente.get(f"/v1/conversas/{conversa_id}/mensagens", headers=auth)
        ).json()

    atual = capturado["entrada"]["messages"][-1]
    assert isinstance(atual.content, str) and "NÃO consegue ver" in atual.content
    avisos = [m for m in mensagens if m["autor"] == "agente"]
    assert len(avisos) == 1 and avisos[0]["agente_id"] == str(bot_id)
    assert "não enxerga imagens" in avisos[0]["conteudo"] and "foto.png" in avisos[0]["conteudo"]
    # O aviso conta como fala antes do turno (o worker não responde duas vezes por engano).
    assert capturado["antes"] >= 2


async def test_anexo_de_outro_usuario_nunca_chega_ao_modelo(
    mundo: Mundo,  # noqa: F811
    pasta,
    monkeypatch,
) -> None:
    email = f"visao-dono-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        dono_alheio = uuid4()
        async with mundo.fabrica() as sessao:  # um usuário qualquer, dono do arquivo
            sessao.add(
                Usuario(
                    id=dono_alheio,
                    nome="Outro",
                    email=f"alheio-{uuid4()}@exemplo.com",
                    senha_hash="x",
                )
            )
            await sessao.commit()
        _, _, _, mensagem_id = await _preparar_turno_com_anexo(
            mundo, cliente, auth, email, pasta, dono_do_anexo=dono_alheio, conteudo=b"SEGREDO"
        )
        capturado = await _rodar_turno(mundo, mensagem_id, monkeypatch)

    atual = capturado["entrada"]["messages"][-1]
    assert atual.content == "O que tem nesta imagem? [grupo]"  # nem lista nem imagem
    assert "SEGREDO" not in json.dumps(str(atual.content))


async def test_agente_sem_ferramenta_de_imagem_nao_a_recebe_sem_modelo_de_imagem(
    mundo: Mundo,  # noqa: F811
    pasta,
) -> None:
    """Sem modelo de imagem conectado a ferramenta nem aparece para o bot."""
    from app.agentes import ContextoAgente
    from app.agentes.montagem import _com_ferramenta_de_imagem

    email = f"sem-imagem-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        await entrar(cliente, mundo.fabrica, email)
        usuario_id = await _usuario_id(mundo, email)
        contexto = ContextoAgente(
            usuario_id=usuario_id, agente_id=uuid4(), conversa_id=uuid4(), papel="individual"
        )
        # Com o modelo falso a checagem é pulada; sem ele, não há modelo de imagem.
        os.environ["SORA_MODELO_FALSO"] = "0"
        try:
            sem = await _com_ferramenta_de_imagem(contexto)
        finally:
            os.environ["SORA_MODELO_FALSO"] = "1"
        assert "gerar_imagem" not in sem.ferramentas_extras
        async with mundo.fabrica() as sessao:
            agente_ids = (
                await sessao.scalars(select(Agente.id).where(Agente.usuario_id == usuario_id))
            ).all()
        assert agente_ids  # a conta existe; só não há modelo de imagem


async def test_imagem_pendente_sobrevive_ao_reinicio_do_worker(
    mundo: Mundo,  # noqa: F811
    pasta,
    seletor_de_imagem,
) -> None:
    """Prumo M5: o registro das saídas do turno fica no Redis, não no processo. Depois de um
    "reinício" (cliente do Redis e módulo recarregados) a mensagem seguinte ainda leva a imagem."""
    import importlib

    from app.ferramentas import ambiente, saidas_do_turno
    from app.ferramentas.falar import Falar, falar
    from app.ferramentas.gerar_imagem import GerarImagem, gerar_imagem

    email = f"reinicio-{uuid4()}@exemplo.com"
    async with httpx.AsyncClient(base_url=mundo.url, timeout=30) as cliente:
        auth = await entrar(cliente, mundo.fabrica, email)
        bot = await _bot(cliente, auth, "Lume")
        usuario_id = await _usuario_id(mundo, email)
        conversa_id = await _conversa(mundo, usuario_id, UUID(bot["id"]))
        contexto = ContextoFerramenta(
            usuario_id=usuario_id, agente_id=UUID(bot["id"]), conversa_id=conversa_id
        )
        await gerar_imagem(GerarImagem(descricao="um gato astronauta"), contexto)

        ambiente.redis_dos_eventos.cache_clear()  # conexão nova, como num processo novo
        importlib.reload(saidas_do_turno)  # e nenhum estado de módulo sobrando

        await falar(Falar(texto="Aqui está."), contexto)
        mensagens = (
            await cliente.get(f"/v1/conversas/{conversa_id}/mensagens", headers=auth)
        ).json()
        assert len([m for m in mensagens if m["autor"] == "agente"][-1]["anexos"]) == 1


async def test_quadros_limitados_sem_apagar_outros_eventos(mundo: Mundo):  # noqa: F811
    from app.computador.eventos import TelaComputadorEvento
    from app.computador.servico import publicar_tela_limitada
    from app.eventos.streams import canal_usuario

    redis = Redis.from_url(mundo.url_redis, decode_responses=True)
    usuario, bot = uuid4(), uuid4()
    canal = canal_usuario(usuario)
    try:
        outro = await redis.xadd(canal, {"event": "outro", "data": "{}"})
        for imagem in ["a", "b", "c", "d", "d"]:
            await publicar_tela_limitada(
                redis,
                TelaComputadorEvento(
                    agente_id=bot,
                    alvo="virtual",
                    ligado=True,
                    miniatura=imagem,
                    em=datetime.now(UTC),
                ),
                usuario,
            )
        entradas = await redis.xrange(canal)
        assert len(entradas) == 4
        assert entradas[0][0] == outro
        assert [json.loads(e[1]["data"])["miniatura"] for e in entradas[1:]] == ["b", "c", "d"]
    finally:
        await redis.aclose()


async def test_anexo_pendente_entre_processos(mundo: Mundo):  # noqa: F811
    import asyncio
    import subprocess
    import sys

    usuario, bot, anexo = uuid4(), uuid4(), uuid4()
    codigo = """
import asyncio, sys
from uuid import UUID
from redis.asyncio import Redis
from app.ferramentas.saidas_do_turno import registrar, recolher
async def main():
    redis = Redis.from_url(sys.argv[1])
    usuario, bot, anexo = map(UUID, sys.argv[2:5])
    try:
        if sys.argv[5] == 'gravar':
            await registrar(usuario, bot, anexo, redis=redis)
        else:
            assert await recolher(usuario, bot, redis=redis) == [anexo]
            assert await recolher(usuario, bot, redis=redis) == []
    finally:
        await redis.aclose()
asyncio.run(main())
"""
    for modo in ("gravar", "ler"):
        resultado = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                "-c",
                codigo,
                mundo.url_redis,
                str(usuario),
                str(bot),
                str(anexo),
                modo,
            ],
            capture_output=True,
            timeout=30,
        )
        assert resultado.returncode == 0, resultado.stderr.decode(errors="replace")
