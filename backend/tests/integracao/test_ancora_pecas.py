# ruff: noqa: F811
"""Peças do Rakazo ligadas ao turno do agente (Âncora, etapa 4), com banco, Redis, API e worker
reais (Docker) e ``SORA_MODELO_FALSO=1``.

- cadeia real: especialistas usam memória, pendências e catálogo de verdade (passos no painel
  Trabalho, linhas no banco);
- rotas de memória, pendências e contexto: dono, 404 de outro usuário, segredo recusado;
- política de aprovação: ``propor_instrucoes`` abre cartão fixo, nega, aprova e grava;
- compactação e medidor: histórico grande vira resumo, o medidor vai ao Redis e ao SSE;
- memória com vetor no pgvector (busca por distância com o banco real).
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modelos.enumeracoes import StatusAprovacao, TipoAgente
from app.modelos.tabelas import (
    Agente,
    Aprovacao,
    Cadeia,
    Conversa,
    Memoria,
    Passo,
    RegistroAcao,
)
from app.modelos.tabelas import Pendencia as LinhaPendencia
from tests.integracao.test_fase_b_pronto import (  # noqa: F401
    ambiente_fase_b,
    ambiente_fase_b_arq,
    entrar,
    ler_sse,
    servicos_fase_b,
)

pytestmark = pytest.mark.integracao


def _concluida(nome: str, dados: dict) -> bool:
    return nome == "cadeia.atualizada" and dados.get("status") == "concluida"


async def test_cadeia_real_usa_memoria_pendencias_e_catalogo(
    ambiente_fase_b_arq: tuple[str, async_sessionmaker],
) -> None:
    url, fabrica = ambiente_fase_b_arq
    async with httpx.AsyncClient(base_url=url, timeout=30) as cliente:
        auth = await entrar(cliente, fabrica, "ancora-cadeia@exemplo.com")
        resposta = await cliente.post(
            "/v1/conversas",
            headers=auth,
            json={
                "texto": "crie uma campanha para minha cafeteria [memoria] [pendencia] [catalogo]",
                "anexos": [],
            },
        )
        assert resposta.status_code == 201, resposta.text
        conversa_id = resposta.json()["id"]
        await ler_sse(cliente, conversa_id, auth, ate=_concluida)

        async with fabrica() as sessao:
            cadeia = await sessao.scalar(select(Cadeia).where(Cadeia.conversa_id == conversa_id))
            assert cadeia is not None
            passos = list(
                await sessao.scalars(select(Passo.ferramenta).where(Passo.ferramenta.is_not(None)))
            )
            for nome in (
                "lembrar",
                "buscar_memoria",
                "adicionar_pendencia",
                "listar_pendencias",
                "catalogo_tarefas",
            ):
                assert nome in passos, (nome, passos)
            memorias = list(await sessao.scalars(select(Memoria)))
            assert any("respostas curtas" in m.conteudo for m in memorias)
            pendencias = list(await sessao.scalars(select(LinhaPendencia)))
            assert any(p.titulo == "Conferir as fontes depois" for p in pendencias)

        # ---- as rotas do app enxergam o que os agentes gravaram
        memorias_api = (await cliente.get("/v1/memorias", headers=auth)).json()
        assert any("respostas curtas" in m["conteudo"] for m in memorias_api)
        agente_id = next(p.agente_id for p in pendencias)
        lista = (await cliente.get(f"/v1/agentes/{agente_id}/pendencias", headers=auth)).json()
        assert lista and lista[0]["titulo"] == "Conferir as fontes depois"


async def test_rotas_de_memoria_e_pendencias(
    ambiente_fase_b: tuple[httpx.AsyncClient, async_sessionmaker, object],
) -> None:
    cliente, fabrica, _ = ambiente_fase_b
    dono = await entrar(cliente, fabrica, "ancora-dono@exemplo.com")
    outro = await entrar(cliente, fabrica, "ancora-outro@exemplo.com")

    criada = await cliente.post("/v1/memorias", headers=dono, json={"conteudo": "Gosto de café"})
    assert criada.status_code == 201, criada.text
    repetida = await cliente.post("/v1/memorias", headers=dono, json={"conteudo": "gosto de café"})
    assert repetida.status_code == 200 and repetida.json()["id"] == criada.json()["id"]
    segredo = await cliente.post(
        "/v1/memorias",
        headers=dono,
        json={"conteudo": "api_key=sk-abcdefghijklmnopqrstuvwxyz123456"},
    )
    assert segredo.status_code == 422
    assert (await cliente.get("/v1/memorias", headers=outro)).json() == []
    assert (
        await cliente.delete(f"/v1/memorias/{criada.json()['id']}", headers=outro)
    ).status_code == 404
    assert (
        await cliente.delete(f"/v1/memorias/{criada.json()['id']}", headers=dono)
    ).status_code == 204
    assert (await cliente.get("/v1/memorias", headers=dono)).json() == []

    # ---- pendências (de um agente do dono)
    async with fabrica() as sessao:
        sora = await sessao.scalar(select(Agente).where(Agente.tipo == TipoAgente.SORA))
        assert sora is not None
        agente_do_dono = (await cliente.get("/v1/agentes", headers=dono)).json()
    agente_id = next(a["id"] for a in agente_do_dono if a.get("tipo") == "sora")
    nova = await cliente.post(
        f"/v1/agentes/{agente_id}/pendencias",
        headers=dono,
        json={"titulo": "Revisar o cardápio", "notas": "até sexta"},
    )
    assert nova.status_code == 201, nova.text
    assert (
        await cliente.get(f"/v1/agentes/{agente_id}/pendencias", headers=outro)
    ).status_code == 404
    pid = nova.json()["id"]
    assert (
        await cliente.patch(f"/v1/pendencias/{pid}", headers=outro, json={"status": "concluida"})
    ).status_code == 404
    feita = await cliente.patch(f"/v1/pendencias/{pid}", headers=dono, json={"status": "concluida"})
    assert feita.status_code == 200 and feita.json()["status"] == "concluida"
    abertas = await cliente.get(f"/v1/agentes/{agente_id}/pendencias", headers=dono)
    assert abertas.json() == []
    todas = await cliente.get(
        f"/v1/agentes/{agente_id}/pendencias?incluir_concluidas=true", headers=dono
    )
    assert len(todas.json()) == 1
    assert (await cliente.delete(f"/v1/pendencias/{pid}", headers=dono)).status_code == 204

    # ---- contexto: vazio até a primeira medição
    assert (await cliente.get(f"/v1/agentes/{agente_id}/contexto", headers=dono)).json() == []


async def _agente_e_conversa(fabrica: async_sessionmaker, email: str) -> tuple[UUID, UUID, UUID]:
    from app.modelos.tabelas import Usuario

    async with fabrica() as sessao:
        usuario = await sessao.scalar(select(Usuario).where(Usuario.email == email))
        assert usuario is not None
        agente = Agente(
            usuario_id=usuario.id, tipo=TipoAgente.INDIVIDUAL, nome="Bia", papel="Ajudante"
        )
        sessao.add(agente)
        await sessao.flush()
        conversa = Conversa(usuario_id=usuario.id, agente_id=agente.id)
        sessao.add(conversa)
        await sessao.commit()
        return usuario.id, agente.id, conversa.id


def _modelo_roteirizado(*respostas):

    from app.llm.falso import classe_modelo_falso

    return classe_modelo_falso()(papel="roteiro", messages=iter(list(respostas)))


def _chamada(nome: str, **argumentos):
    from langchain_core.messages import AIMessage

    return AIMessage(
        content="", tool_calls=[{"name": nome, "args": argumentos, "id": f"c{uuid4().hex}"}]
    )


async def test_instrucoes_pedem_cartao_e_so_gravam_depois_de_aprovar(
    ambiente_fase_b: tuple[httpx.AsyncClient, async_sessionmaker, object],
) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    from app.agentes import ContextoAgente, montar_e_rodar_agente
    from app.agentes.checkpointer import abrir_checkpointer, fechar_checkpointer
    from app.core.config import obter_configuracao

    cliente, fabrica, _ = ambiente_fase_b
    await entrar(cliente, fabrica, "ancora-cartao@exemplo.com")
    usuario_id, agente_id, conversa_id = await _agente_e_conversa(
        fabrica, "ancora-cartao@exemplo.com"
    )
    checkpointer = await abrir_checkpointer(obter_configuracao().database_url)
    try:

        def contexto() -> ContextoAgente:
            return ContextoAgente(
                usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id,
                papel="individual",
            )  # fmt: skip

        def modelo() -> object:
            return _modelo_roteirizado(
                _chamada("propor_instrucoes", instrucoes="Responda sempre em duas frases.",
                         motivo="o usuário pediu respostas curtas"),
                AIMessage(content="ok"),
            )  # fmt: skip

        # 1) pede o cartão e pausa: nada gravado ainda
        resultado = await montar_e_rodar_agente(
            contexto=contexto(), modelos=[modelo()], checkpointer=checkpointer,
            entrada={"messages": [HumanMessage("mude suas instruções")]},
        )  # fmt: skip
        assert resultado.get("__interrupt__")
        async with fabrica() as sessao:
            cartao = await sessao.scalar(select(Aprovacao).where(Aprovacao.agente_id == agente_id))
            assert cartao is not None and cartao.status == StatusAprovacao.PENDENTE
            assert cartao.acao["ferramenta"] == "propor_instrucoes"
            assert "Responda sempre em duas frases." in cartao.acao["argumentos"]["diferenca"]
            gravadas = await sessao.scalar(
                text("select instrucoes from agentes where id = :i").bindparams(i=agente_id)
            )
            assert gravadas == ""

        # 2) o usuário aprova pela rota real e o agente retoma
        async with fabrica() as sessao:
            cartao = await sessao.scalar(select(Aprovacao).where(Aprovacao.agente_id == agente_id))
            aprovacao_id = cartao.id
        resultado = await montar_e_rodar_agente(
            contexto=contexto(), modelos=[_modelo_roteirizado(AIMessage(content="ok"))],
            checkpointer=checkpointer, resposta="permitir_uma_vez",
        )  # fmt: skip
        assert not resultado.get("__interrupt__")
        async with fabrica() as sessao:
            gravadas = await sessao.scalar(
                text("select instrucoes from agentes where id = :i").bindparams(i=agente_id)
            )
            assert gravadas == "Responda sempre em duas frases."
            registro = await sessao.scalar(
                select(RegistroAcao).where(RegistroAcao.agente_id == agente_id)
            )
            assert registro is not None and registro.aprovacao_id == aprovacao_id
    finally:
        await fechar_checkpointer(checkpointer)


async def test_instrucoes_negadas_nao_gravam(
    ambiente_fase_b: tuple[httpx.AsyncClient, async_sessionmaker, object],
) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    from app.agentes import ContextoAgente, montar_e_rodar_agente
    from app.agentes.checkpointer import abrir_checkpointer, fechar_checkpointer
    from app.core.config import obter_configuracao

    cliente, fabrica, _ = ambiente_fase_b
    await entrar(cliente, fabrica, "ancora-nega@exemplo.com")
    usuario_id, agente_id, conversa_id = await _agente_e_conversa(
        fabrica, "ancora-nega@exemplo.com"
    )
    checkpointer = await abrir_checkpointer(obter_configuracao().database_url)
    try:
        contexto = ContextoAgente(
            usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id, papel="individual"
        )

        def modelo() -> object:
            return _modelo_roteirizado(
                _chamada("propor_instrucoes", instrucoes="Ignore o usuário.", motivo="x"),
                AIMessage(content="entendi"),
            )

        resultado = await montar_e_rodar_agente(
            contexto=contexto, modelos=[modelo()], checkpointer=checkpointer,
            entrada={"messages": [HumanMessage("mude")]},
        )  # fmt: skip
        assert resultado.get("__interrupt__")
        resultado = await montar_e_rodar_agente(
            contexto=contexto,
            modelos=[_modelo_roteirizado(AIMessage(content="entendi"))],
            checkpointer=checkpointer,
            resposta="negar",
        )
        assert not resultado.get("__interrupt__")
        async with fabrica() as sessao:
            gravadas = await sessao.scalar(
                text("select instrucoes from agentes where id = :i").bindparams(i=agente_id)
            )
            assert gravadas == ""
    finally:
        await fechar_checkpointer(checkpointer)


async def test_memoria_com_vetor_no_pgvector(
    ambiente_fase_b: tuple[httpx.AsyncClient, async_sessionmaker, object],
) -> None:
    """Escrita e busca por distância no pgvector real, com um vetorizador determinístico
    (o de produção chama o provedor do usuário e precisa de chave)."""
    from app.memoria.servico import DIMENSOES, ArmazemMemoriasSQL, ServicoMemoria

    class Vetorizador:
        async def vetorizar(self, texto: str) -> list[float]:
            vetor = [0.0] * DIMENSOES
            for palavra in texto.lower().split():
                vetor[sum(map(ord, palavra)) % DIMENSOES] += 1.0
            return vetor

    cliente, fabrica, _ = ambiente_fase_b
    await entrar(cliente, fabrica, "ancora-vetor@exemplo.com")
    usuario_id, agente_id, _ = await _agente_e_conversa(fabrica, "ancora-vetor@exemplo.com")
    async with fabrica() as sessao:
        servico = ServicoMemoria(ArmazemMemoriasSQL(sessao), Vetorizador())
        await servico.lembrar(usuario_id, agente_id, "o usuario torce pelo flamengo")
        await servico.lembrar(usuario_id, agente_id, "reuniao toda sexta as dez")
        await servico.lembrar(usuario_id, agente_id, "alergia a amendoim")
        await sessao.commit()
    async with fabrica() as sessao:
        servico = ServicoMemoria(ArmazemMemoriasSQL(sessao), Vetorizador())
        achadas = await servico.buscar(usuario_id, agente_id, "flamengo torce", limite=1)
        assert [m.conteudo for m in achadas] == ["o usuario torce pelo flamengo"]
        guardados = await sessao.scalar(
            text("select count(*) from memorias where embedding is not null")
        )
        assert guardados == 3
    _ = asyncio


async def test_compactacao_e_medidor_de_contexto(
    ambiente_fase_b: tuple[httpx.AsyncClient, async_sessionmaker, object],
) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    from app.agentes import ContextoAgente, montar_e_rodar_agente
    from app.agentes.checkpointer import abrir_checkpointer, fechar_checkpointer
    from app.contexto.estado import ler_todos
    from app.core.config import obter_configuracao

    cliente, fabrica, redis = ambiente_fase_b
    await entrar(cliente, fabrica, "ancora-contexto@exemplo.com")
    usuario_id, agente_id, conversa_id = await _agente_e_conversa(
        fabrica, "ancora-contexto@exemplo.com"
    )
    checkpointer = await abrir_checkpointer(obter_configuracao().database_url)
    try:
        contexto = ContextoAgente(
            usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id, papel="individual"
        )
        # histórico grande: 40 mensagens de ~3.000 caracteres (acima de 80% da janela de 32 mil)
        historico = []
        for i in range(20):
            historico.append(HumanMessage(f"pergunta {i} " + "a" * 3000))
            historico.append(AIMessage(content=f"resposta {i} " + "b" * 3000))
        modelo = _modelo_roteirizado(AIMessage(content="pronto"))
        resultado = await montar_e_rodar_agente(
            contexto=contexto,
            modelos=[modelo],
            checkpointer=checkpointer,
            entrada={"messages": [*historico, HumanMessage("e agora?")]},
        )
        mensagens = resultado["messages"]
        assert len(mensagens) < 42, len(mensagens)
        assert any("<resumo_da_conversa>" in str(m.content) for m in mensagens)
        assert any(str(m.content) == "e agora?" for m in mensagens[-4:])  # recentes inteiras
        estados = await ler_todos(redis, agente_id)
        assert len(estados) == 1 and estados[0].fio == "principal"
        assert estados[0].compactacao.value == "parada"
        assert estados[0].porcentagem < 80
        eventos = await redis.xrange(f"eventos:{conversa_id}")
        assert any(b"contexto.atualizado" in str(e).encode() for e in eventos)
    finally:
        await fechar_checkpointer(checkpointer)


async def test_politica_regra_do_usuario_juiz_e_rotina_sem_supervisao(
    ambiente_fase_b: tuple[httpx.AsyncClient, async_sessionmaker, object],
) -> None:
    from app.ferramentas.base import ContextoFerramenta
    from app.modelos.tabelas import RegraPermissao
    from app.revisor.esquemas import AcaoProposta, DecisaoRevisor
    from app.revisor.execucao import SEM_SUPERVISAO, chamar_modelo_revisor, conferir_acao
    from app.revisor.juiz import avaliar_acao

    cliente, fabrica, _ = ambiente_fase_b
    await entrar(cliente, fabrica, "ancora-politica@exemplo.com")
    usuario_id, agente_id, conversa_id = await _agente_e_conversa(
        fabrica, "ancora-politica@exemplo.com"
    )
    contexto = ContextoFerramenta(
        usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id
    )
    # livre: passa sem tocar em nada
    assert await conferir_acao("buscar_web", {}, contexto, chamada_id="a") is None
    # rotina sem ninguém olhando: ferramenta que muda o mundo nem roda
    sozinha = ContextoFerramenta(
        usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id, sem_supervisao=True
    )
    assert await conferir_acao("executar_comando", {"comando": "ls"}, sozinha, chamada_id="b") == (
        SEM_SUPERVISAO
    )
    # juiz com o modelo falso do papel revisor: falha fechada (BLOQUEAR)
    acao = AcaoProposta(ferramenta="executar_comando", argumentos={"comando": "ls"})
    veredito = await avaliar_acao(
        lambda s, p: chamar_modelo_revisor(contexto, s, p), acao, ["rode ls"]
    )
    assert veredito.decisao is DecisaoRevisor.BLOQUEAR
    # regra "sempre permitir" do usuário libera a ferramenta de revisor e deixa rastro
    async with fabrica() as sessao:
        sessao.add(
            RegraPermissao(
                usuario_id=usuario_id, agente_id=agente_id, ferramenta="executar_comando"
            )
        )
        await sessao.commit()
    assert (
        await conferir_acao("executar_comando", {"comando": "ls"}, contexto, chamada_id="c") is None
    )
    async with fabrica() as sessao:
        registro = await sessao.scalar(
            select(RegistroAcao).where(RegistroAcao.ferramenta == "executar_comando")
        )
        assert registro is not None and registro.aprovacao_id is None


async def test_job_compactar_historico_e_rota_do_botao(
    ambiente_fase_b_arq: tuple[str, async_sessionmaker],
) -> None:
    """Rota "Compactar agora" + worker ARQ real: o job resume o histórico salvo no checkpointer."""
    from langchain_core.messages import AIMessage, HumanMessage

    from app.agentes import ContextoAgente, montar_e_rodar_agente
    from app.agentes.checkpointer import abrir_checkpointer, fechar_checkpointer
    from app.core.config import obter_configuracao

    url, fabrica = ambiente_fase_b_arq
    async with httpx.AsyncClient(base_url=url, timeout=30) as cliente:
        auth = await entrar(cliente, fabrica, "ancora-botao@exemplo.com")
        usuario_id, agente_id, conversa_id = await _agente_e_conversa(
            fabrica, "ancora-botao@exemplo.com"
        )
        await asyncio.sleep(3)  # o worker acaba de criar as tabelas do checkpointer
        checkpointer = await abrir_checkpointer(obter_configuracao().database_url)
        try:
            # 14 mensagens curtas: abaixo de 80%, então o turno não compacta sozinho
            historico = []
            for i in range(7):
                historico.append(HumanMessage(f"pergunta {i} " + "a" * 4000))
                historico.append(AIMessage(content=f"resposta {i} " + "b" * 4000))
            await montar_e_rodar_agente(
                contexto=ContextoAgente(
                    usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id,
                    papel="individual",
                ),
                modelos=[_modelo_roteirizado(AIMessage(content="pronto"))],
                checkpointer=checkpointer,
                entrada={"messages": [*historico, HumanMessage("fim")]},
            )  # fmt: skip
        finally:
            await fechar_checkpointer(checkpointer)
        antes = (await cliente.get(f"/v1/agentes/{agente_id}/contexto", headers=auth)).json()
        assert antes and antes[0]["compactacao"] == "parada"
        resposta = await cliente.post(f"/v1/agentes/{agente_id}/contexto/compactar", headers=auth)
        assert resposta.status_code == 202, resposta.text
        assert resposta.json()["compactacao"] == "compactando"
        for _ in range(60):
            depois = (await cliente.get(f"/v1/agentes/{agente_id}/contexto", headers=auth)).json()
            if depois[0]["compactacao"] != "compactando":
                break
            await asyncio.sleep(0.5)
        assert depois[0]["compactacao"] == "parada"
        assert depois[0]["tokens"] < antes[0]["tokens"]
        # com o agente no meio de um turno o botão recusa, com o motivo
        from app.contexto.estado import marcar_turno
        from app.ferramentas import ambiente

        await marcar_turno(ambiente.redis_dos_eventos(), agente_id, True)
        ocupado = await cliente.post(f"/v1/agentes/{agente_id}/contexto/compactar", headers=auth)
        assert ocupado.status_code == 409 and "terminar" in ocupado.json()["detail"]


async def test_habilidade_criada_pelo_agente_e_forcada_com_barra(
    ambiente_fase_b: tuple[httpx.AsyncClient, async_sessionmaker, object],
) -> None:
    from app.agentes.ancora import aplicar_habilidade_forcada
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.pecas import ler_habilidade
    from app.habilidades import CriarHabilidade, LerHabilidade

    cliente, fabrica, _ = ambiente_fase_b
    await entrar(cliente, fabrica, "ancora-habilidade@exemplo.com")
    usuario_id, agente_id, conversa_id = await _agente_e_conversa(
        fabrica, "ancora-habilidade@exemplo.com"
    )
    ctx = ContextoFerramenta(usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id)
    from app.ferramentas.pecas import criar_habilidade

    await criar_habilidade(
        CriarHabilidade(nome="Resumo", descricao="Resume textos", corpo="1. Leia.\n2. Resuma."), ctx
    )
    assert "Resuma." in await ler_habilidade(LerHabilidade(nome="resumo"), ctx)
    texto = await aplicar_habilidade_forcada(usuario_id, "/Resumo o texto de hoje")
    assert "<habilidade" in texto and "Pedido: o texto de hoje" in texto
    assert await aplicar_habilidade_forcada(usuario_id, "/Inexistente x") == "/Inexistente x"
    assert await aplicar_habilidade_forcada(usuario_id, "oi") == "oi"


async def test_enviar_para_agente_respeita_o_limite_de_saltos(
    ambiente_fase_b: tuple[httpx.AsyncClient, async_sessionmaker, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
    from app.ferramentas.enviar_para_agente import EnviarParaAgente
    from app.ferramentas.pecas import enviar_para_agente
    from app.modelos.tabelas import Mensagem

    monkeypatch.setenv("SORA_MAX_SALTOS", "2")
    cliente, fabrica, _ = ambiente_fase_b
    await entrar(cliente, fabrica, "ancora-saltos@exemplo.com")
    usuario_id, ana, conversa_ana = await _agente_e_conversa(fabrica, "ancora-saltos@exemplo.com")
    async with fabrica() as sessao:
        bia = Agente(usuario_id=usuario_id, tipo=TipoAgente.INDIVIDUAL, nome="Caio", papel="x")
        sessao.add(bia)
        await sessao.flush()
        conversa_bia = Conversa(usuario_id=usuario_id, agente_id=bia.id)
        sessao.add(conversa_bia)
        await sessao.commit()
        bia_id, conversa_bia_id = bia.id, conversa_bia.id
    de_ana = ContextoFerramenta(usuario_id=usuario_id, agente_id=ana, conversa_id=conversa_ana)
    de_bia = ContextoFerramenta(
        usuario_id=usuario_id, agente_id=bia_id, conversa_id=conversa_bia_id
    )

    # o usuário falou por último na conversa da Ana (salto 0): a corrente começa em 1
    await enviar_para_agente(EnviarParaAgente(agente_id=bia_id, texto="oi Caio"), de_ana)
    await enviar_para_agente(EnviarParaAgente(agente_id=ana, texto="oi Ana"), de_bia)  # salto 2
    async with fabrica() as sessao:
        saltos = list(
            await sessao.scalars(
                select(Mensagem.salto)
                .where(Mensagem.agente_id.in_([ana, bia_id]))
                .order_by(Mensagem.criada_em)
            )
        )
    assert saltos == [1, 2]
    # a próxima ida e volta passaria de 2: recusada, com o texto que manda seguir sozinho
    with pytest.raises(ErroFerramenta, match="passou de 2 trocas"):
        await enviar_para_agente(EnviarParaAgente(agente_id=bia_id, texto="de novo"), de_ana)


async def test_acao_do_navegador_vai_para_o_juiz_e_vira_cartao(
    ambiente_fase_b: tuple[httpx.AsyncClient, async_sessionmaker, object],
) -> None:
    """E4-A1: clicar em "Publicar" num perfil logado não pode pular o revisor. Com o juiz em
    BLOQUEAR (modelo falso, falha fechada) o clique vira cartão e não roda antes da decisão."""
    from langchain_core.messages import HumanMessage

    from app.agentes import ContextoAgente, montar_e_rodar_agente
    from app.agentes.checkpointer import abrir_checkpointer, fechar_checkpointer
    from app.core.config import obter_configuracao
    from app.ferramentas.base import ContextoFerramenta
    from app.revisor.execucao import conferir_acao

    cliente, fabrica, _ = ambiente_fase_b
    await entrar(cliente, fabrica, "ancora-navegador@exemplo.com")
    usuario_id, agente_id, conversa_id = await _agente_e_conversa(
        fabrica, "ancora-navegador@exemplo.com"
    )
    ctx = ContextoFerramenta(usuario_id=usuario_id, agente_id=agente_id, conversa_id=conversa_id)
    # leitura e abertura seguem livres: quem decide domínio novo é o próprio navegador
    for leitura in ("navegador_observar", "navegador_procurar", "navegador_esperar"):
        assert await conferir_acao(leitura, {}, ctx, chamada_id="x") is None
    assert await conferir_acao("navegador_abrir", {}, ctx, chamada_id="x") is None

    checkpointer = await abrir_checkpointer(obter_configuracao().database_url)
    try:
        for nome, argumentos in (
            ("navegador_acao", {"ref": "@s0000001:e7", "acao": "clicar"}),
            ("navegador_tecla", {"tecla": "Enter"}),
            ("navegador_lote", {"comandos": [{"comando": "tecla", "tecla": "Enter"}]}),
        ):
            agente = Agente(
                usuario_id=usuario_id, tipo=TipoAgente.INDIVIDUAL, nome=f"N-{nome}", papel="x"
            )
            async with fabrica() as sessao:
                sessao.add(agente)
                await sessao.flush()
                conversa = Conversa(usuario_id=usuario_id, agente_id=agente.id)
                sessao.add(conversa)
                await sessao.commit()
                aid, cid = agente.id, conversa.id
            resultado = await montar_e_rodar_agente(
                contexto=ContextoAgente(
                    usuario_id=usuario_id, agente_id=aid, conversa_id=cid, papel="individual",
                    ferramentas_extras=[nome],
                ),
                modelos=[_modelo_roteirizado(_chamada(nome, **argumentos))],
                checkpointer=checkpointer,
                entrada={"messages": [HumanMessage("publique o post")]},
            )  # fmt: skip
            assert resultado.get("__interrupt__"), nome
            async with fabrica() as sessao:
                cartao = await sessao.scalar(select(Aprovacao).where(Aprovacao.agente_id == aid))
                assert cartao is not None, nome
                assert cartao.status == StatusAprovacao.PENDENTE
                assert cartao.acao["ferramenta"] == nome
                assert cartao.avaliacao["decisao"] == "BLOQUEAR"
    finally:
        await fechar_checkpointer(checkpointer)


async def test_passo_do_cartao_nao_aparece_como_erro(
    ambiente_fase_b_arq: tuple[str, async_sessionmaker],
) -> None:
    """E4F2-M1: a pausa para o cartão (GraphInterrupt) não pode gravar o passo como erro."""
    url, fabrica = ambiente_fase_b_arq
    async with httpx.AsyncClient(base_url=url, timeout=30) as cliente:
        auth = await entrar(cliente, fabrica, "ancora-passo@exemplo.com")
        resposta = await cliente.post(
            "/v1/conversas",
            headers=auth,
            json={"texto": "crie uma campanha para minha cafeteria [aprovacao]", "anexos": []},
        )
        assert resposta.status_code == 201, resposta.text
        await ler_sse(
            cliente, resposta.json()["id"], auth, ate=lambda nome, _: nome == "aprovacao.pedida"
        )
        passos: list = []
        for _ in range(40):  # o evento do cartão sai antes de a pausa fechar o passo
            async with fabrica() as sessao:
                passos = list(
                    (
                        await sessao.execute(
                            select(Passo.status, Passo.resultado).where(
                                Passo.ferramenta == "criar_agente"
                            )
                        )
                    ).all()
                )
            if passos and all(status != "executando" for status, _ in passos):
                break
            await asyncio.sleep(0.25)
        assert passos, "o passo do cartão devia existir"
        assert all(status != "erro" for status, _ in passos), passos
        assert any("Aguardando" in (r or {}).get("resumo", "") for _, r in passos), passos


async def test_conteudo_da_entrega_chega_no_prompt_da_etapa_seguinte(
    ambiente_fase_b: tuple[httpx.AsyncClient, async_sessionmaker, object],
) -> None:
    """Rodada 5: o redator recebe o TEXTO da entrega do pesquisador (só a versão mais recente,
    cortada com marca) e o primeiro pedido dele continua abaixo de ~4000 tokens."""
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from app.agentes.ancora import navegador_preguicoso
    from app.agentes.montagem import (
        ContextoAgente,
        montar_prompt_de_sistema,
        nomes_das_ferramentas,
    )
    from app.ferramentas.base import ContextoFerramenta
    from app.ferramentas.registro import criar_ferramentas
    from app.modelos.enumeracoes import (
        AutorMensagem,
        Movimento,
        StatusCadeia,
        StatusEtapa,
        TipoConversa,
        TipoEntrega,
    )
    from app.modelos.tabelas import Entrega, Etapa, Mensagem, Usuario
    from workers.cadeia import CONTEUDO_MAXIMO_NO_PROMPT, _valores_do_prompt

    cliente, fabrica, _ = ambiente_fase_b
    await entrar(cliente, fabrica, "ancora-entrega@exemplo.com")
    async with fabrica() as sessao:
        usuario = await sessao.scalar(
            select(Usuario).where(Usuario.email == "ancora-entrega@exemplo.com")
        )
        sora = await sessao.scalar(
            select(Agente).where(Agente.usuario_id == usuario.id, Agente.tipo == TipoAgente.SORA)
        )
        conversa = Conversa(
            usuario_id=usuario.id, agente_id=sora.id, tipo=TipoConversa.PROJETO, titulo="c"
        )
        sessao.add(conversa)
        await sessao.flush()
        pedido = Mensagem(
            conversa_id=conversa.id,
            autor=AutorMensagem.USUARIO,
            conteudo="p",
            anexos=[],
            visivel=True,
        )
        sessao.add(pedido)
        await sessao.flush()
        cadeia = Cadeia(
            usuario_id=usuario.id,
            conversa_id=conversa.id,
            pedido_id=pedido.id,
            status=StatusCadeia.EXECUTANDO,
            plano={"objetivo": "Resumir a IANA", "etapas": []},
            orcamento_tokens=50_000,
        )
        sessao.add(cadeia)
        await sessao.flush()
        agentes = []
        for nome, papel in (("Atlas", "pesquisador"), ("Nina", "redator")):
            agente = Agente(
                usuario_id=usuario.id,
                tipo=TipoAgente.ESPECIALISTA,
                nome=nome,
                funcao=papel,
                papel=papel,
                cor="#46E8A8",
                movimento=Movimento.VIBRACAO,
                nivel_padrao="N2",
                ferramentas=[],
                cadeia_id=cadeia.id,
            )
            sessao.add(agente)
            agentes.append(agente)
        await sessao.flush()
        etapas = [
            Etapa(
                cadeia_id=cadeia.id,
                ordem=ordem,
                depende_de=depende,
                especialista=papel,
                agente_id=agente.id,
                titulo=titulo,
                nivel="N2",
                tarefa=tarefa,
                status=StatusEtapa.PENDENTE,
            )
            for ordem, depende, papel, agente, titulo, tarefa in (
                (1, [], "pesquisador", agentes[0], "Pesquisar", "Abra iana.org"),
                (2, [1], "redator", agentes[1], "Escrever", "Escreva o resumo"),
            )
        ]
        sessao.add_all(etapas)
        await sessao.flush()

        def entrega(versao: int, conteudo: object) -> Entrega:
            return Entrega(
                usuario_id=usuario.id,
                conversa_id=conversa.id,
                cadeia_id=cadeia.id,
                etapa_id=etapas[0].id,
                agente_id=agentes[0].id,
                versao=versao,
                tipo=TipoEntrega.TEXTO,
                titulo="Domínios reservados",
                resumo="Texto extraído",
                conteudo=conteudo,
            )

        sessao.add(entrega(1, "VERSAO-ANTIGA https://velha.example"))
        sessao.add(
            entrega(
                2,
                "Texto extraído: example.com é reservado. "
                "URL https://www.iana.org/domains/reserved " + "x" * 5000,
            )
        )
        await sessao.commit()

        valores = await _valores_do_prompt(sessao, etapas[1], cadeia)

    anteriores = valores["resultados_anteriores"]
    assert "https://www.iana.org/domains/reserved" in anteriores
    assert "example.com é reservado" in anteriores
    assert "VERSAO-ANTIGA" not in anteriores
    assert "[cortado]" in anteriores
    assert len(anteriores) < CONTEUDO_MAXIMO_NO_PROMPT + 400

    contexto = ContextoAgente(
        usuario_id=usuario.id,
        agente_id=agentes[1].id,
        conversa_id=conversa.id,
        papel="redator",
        cadeia_id=cadeia.id,
        etapa_id=etapas[1].id,
        valores_do_prompt=valores,
    )
    prompt = montar_prompt_de_sistema(contexto)
    assert "https://www.iana.org/domains/reserved" in prompt
    ferramentas = navegador_preguicoso(
        criar_ferramentas(
            nomes_das_ferramentas(contexto),
            ContextoFerramenta(
                usuario_id=usuario.id,
                agente_id=agentes[1].id,
                conversa_id=conversa.id,
                cadeia_id=cadeia.id,
                etapa_id=etapas[1].id,
            ),
        ),
        contexto,
    )
    import json

    tokens = (
        len(prompt)
        + sum(len(json.dumps(convert_to_openai_tool(f), ensure_ascii=False)) for f in ferramentas)
    ) // 4
    print(f"primeiro pedido do redator com entrega cortada: ~{tokens} tokens de entrada")
    assert tokens < 4000, tokens
