"""Peças da fase 2 adaptadas do Rakazo (docs/referencias/rakazo.md): memória, mensagens
entre agentes, agenda e resposta silenciosa, pendências, habilidades e trabalho parado.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.enviar_para_agente import (
    EnviarParaAgente,
    diretorio_de_colegas,
    preparar_envio,
)
from app.habilidades import (
    Playbook,
    habilidade_forcada,
    instrucao_de_habilidades,
    ler_skill_md,
    mencoes_em_rotina,
    montar_skill_md,
    playbook_para_markdown,
)
from app.memoria.servico import (
    ArmazemMemoriasEmMemoria,
    RegistroMemoria,
    ServicoMemoria,
    validar_conteudo,
)
from app.orquestrador import travados as t
from app.orquestrador.saltos import SaltosEsgotados
from app.pendencias import (
    AdicionarPendencia,
    AtualizarPendencia,
    aplicar_atualizacao,
    contexto_de_pendencias,
    nova_pendencia,
)
from app.rotinas import agenda as a
from app.rotinas.silencio import SEM_RESPOSTA, e_silencio, limpar_resposta

AGORA = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)  # 12h em São Paulo


# ---------- memória ----------


async def test_lembrar_buscar_e_esquecer() -> None:
    servico = ServicoMemoria(ArmazemMemoriasEmMemoria())
    usuario, agente, outro = uuid4(), uuid4(), uuid4()
    primeira = await servico.lembrar(usuario, agente, "  Prefere relatórios   curtos ")
    assert primeira.conteudo == "Prefere relatórios curtos" and primeira.travada
    assert (await servico.lembrar(usuario, agente, "prefere RELATÓRIOS curtos")).id == primeira.id
    await servico.lembrar(usuario, None, "Mora em São Paulo")
    await servico.lembrar(outro, None, "Relatórios longos")  # outro usuário
    achadas = await servico.buscar(usuario, agente, "relatorios")
    assert [m.conteudo for m in achadas] == ["Prefere relatórios curtos"]
    assert len(await servico.buscar(usuario, uuid4(), "relatorios")) == 0  # memória de outro agente
    assert [m.conteudo for m in await servico.buscar(usuario, uuid4(), "paulo")] == [
        "Mora em São Paulo"
    ]
    assert await servico.esquecer(usuario, primeira.id)
    assert not await servico.esquecer(usuario, primeira.id)
    assert not await servico.esquecer(outro, primeira.id)
    assert await servico.buscar(usuario, agente, "relatorios") == []
    contexto = ServicoMemoria.contexto(await servico.buscar(usuario, None, "paulo"))
    assert "<memorias_lembradas>" in contexto and "não instrução" in contexto


def test_memoria_recusa_segredos_e_excessos() -> None:
    with pytest.raises(ErroFerramenta, match="senhas"):
        validar_conteudo("minha api_key=abc123")
    with pytest.raises(ErroFerramenta):
        validar_conteudo("x" * 501)
    with pytest.raises(ErroFerramenta):
        validar_conteudo("   ")


# ---------- enviar para agente ----------


def test_enviar_para_agente() -> None:
    contexto = ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4())
    colega = uuid4()
    args = EnviarParaAgente(agente_id=colega, texto=" achei 4 referências ")
    envio = preparar_envio(args, contexto, salto_de_origem=None, colegas={colega}, chamada_id="c1")
    assert envio.salto == 1 and envio.texto == "achei 4 referências"
    assert envio.chave_entrega == f"agente:{contexto.agente_id}:c1"
    with pytest.raises(SaltosEsgotados):
        preparar_envio(args, contexto, salto_de_origem=6, colegas={colega}, chamada_id="c2")
    with pytest.raises(ErroFerramenta, match="colegas"):
        preparar_envio(args, contexto, salto_de_origem=0, colegas=set(), chamada_id="c3")
    para_si = EnviarParaAgente(agente_id=contexto.agente_id, texto="oi")
    with pytest.raises(ErroFerramenta, match="si mesmo"):
        preparar_envio(
            para_si, contexto, salto_de_origem=0, colegas={contexto.agente_id}, chamada_id="c4"
        )


def test_diretorio_de_colegas() -> None:
    colegas = [(uuid4(), f"Agente {i}", "Pesquisa") for i in range(10)]
    texto = diretorio_de_colegas(colegas, limite_caracteres=200)
    assert texto.startswith("Seus colegas") and "… e mais" in texto
    assert diretorio_de_colegas([]) == ""


# ---------- agenda e silêncio ----------


def test_um_jeito_so_de_marcar_o_tempo() -> None:
    ok = a.Agendar(titulo="t", pedido="p", cron="0 9 * * 1", em="", daqui_minutos=None)
    assert ok.cron == "0 9 * * 1" and ok.em is None
    with pytest.raises(ValidationError):
        a.Agendar(titulo="t", pedido="p", cron="0 9 * * 1", daqui_minutos=5)
    with pytest.raises(ValidationError):
        a.Agendar(titulo="t", pedido="p")
    with pytest.raises(ValidationError):
        a.Agendar(titulo="t", pedido="p", a_cada=2)


def test_planejar_cron_no_fuso_do_usuario() -> None:
    plano = a.planejar(a.Agendar(titulo="t", pedido="p", cron="0 9 * * *"), agora=AGORA)
    assert plano.tipo == "cron"
    assert plano.proxima_execucao == datetime(2026, 10, 18, 12, 0, tzinfo=UTC)  # 9h BRT
    seguinte = a.proxima_depois(plano, plano.proxima_execucao)
    assert seguinte == datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    with pytest.raises(ErroFerramenta, match="5 minutos"):
        a.planejar(a.Agendar(titulo="t", pedido="p", cron="* * * * *"), agora=AGORA)
    with pytest.raises(ErroFerramenta, match="inválido"):
        a.planejar(a.Agendar(titulo="t", pedido="p", cron="todo dia"), agora=AGORA)


def test_planejar_intervalo_unico_e_atrasos() -> None:
    intervalo = a.planejar(
        a.Agendar(titulo="t", pedido="p", a_cada=2, unidade="horas"), agora=AGORA
    )
    assert intervalo.proxima_execucao == AGORA + timedelta(hours=2)
    # worker parado por 5 h: pula para a próxima no futuro, sem disparar as perdidas
    proxima = a.proxima_depois(intervalo, AGORA + timedelta(hours=7))
    assert proxima == AGORA + timedelta(hours=8)
    with pytest.raises(ErroFerramenta, match="1 minuto"):
        a.planejar(a.Agendar(titulo="t", pedido="p", a_cada=0.5, unidade="minutos"), agora=AGORA)
    unico = a.planejar(a.Agendar(titulo="t", pedido="p", daqui_minutos=10), agora=AGORA)
    assert unico.tipo == "unico" and a.proxima_depois(unico, AGORA) is None
    local = a.planejar(
        a.Agendar(titulo="t", pedido="p", em=datetime(2026, 10, 20, 8, 30)), agora=AGORA
    )
    assert local.proxima_execucao == datetime(2026, 10, 20, 11, 30, tzinfo=UTC)
    with pytest.raises(ErroFerramenta, match="passou"):
        a.planejar(a.Agendar(titulo="t", pedido="p", em=AGORA - timedelta(minutes=1)), agora=AGORA)
    with pytest.raises(ErroFerramenta):
        a.conferir_limite(a.MAX_AGENDAMENTOS_ATIVOS)
    assert a.fuso_valido("Lugar/Inexistente") == a.FUSO_PADRAO


def test_resposta_silenciosa() -> None:
    assert e_silencio(f"  {SEM_RESPOSTA} ")
    assert e_silencio(SEM_RESPOSTA * 2)
    assert limpar_resposta(SEM_RESPOSTA) is None
    assert limpar_resposta(f"{SEM_RESPOSTA} Achei 2 notícias. {SEM_RESPOSTA}") == (
        "Achei 2 notícias."
    )
    assert limpar_resposta(f"{SEM_RESPOSTA}_PADRAO é o nome") == f"{SEM_RESPOSTA}_PADRAO é o nome"
    assert limpar_resposta("Tudo certo") == "Tudo certo"


# ---------- pendências ----------


def test_pendencias() -> None:
    usuario, agente = uuid4(), uuid4()
    pendencia = nova_pendencia(usuario, agente, AdicionarPendencia(titulo=" Revisar <logo> "), 0)
    assert pendencia.titulo == "Revisar <logo>"
    with pytest.raises(ErroFerramenta):
        nova_pendencia(usuario, agente, AdicionarPendencia(titulo="x"), 100)
    aplicar_atualizacao(pendencia, AtualizarPendencia(pendencia_id=pendencia.id, notas="cor azul"))
    with pytest.raises(ErroFerramenta):
        aplicar_atualizacao(pendencia, AtualizarPendencia(pendencia_id=pendencia.id))
    contexto = contexto_de_pendencias([pendencia])
    assert contexto is not None and "&lt;logo&gt;" in contexto and "cor azul" in contexto
    pendencia.status = "concluida"
    assert contexto_de_pendencias([pendencia]) is None


def test_contexto_de_pendencias_respeita_o_limite() -> None:
    usuario, agente = uuid4(), uuid4()
    muitas = [
        nova_pendencia(usuario, agente, AdicionarPendencia(titulo=f"tarefa {i} " + "x" * 80), 0)
        for i in range(60)
    ]
    contexto = contexto_de_pendencias(muitas)
    assert contexto is not None and len(contexto.encode()) <= 4 * 1024
    assert contexto.endswith("</pendencias_abertas>")


# ---------- habilidades ----------


def test_skill_md_ida_e_volta() -> None:
    texto = montar_skill_md(
        "Resumo semanal", "Quando pedirem o resumo", "1. Ler\n2. Resumir", {"versao": 2}
    )
    assert texto.startswith("---\nname: Resumo semanal\ndescription: Quando pedirem o resumo\n")
    lida = ler_skill_md(texto)
    assert lida.nome == "Resumo semanal" and lida.frontmatter["versao"] == 2
    assert lida.corpo.strip() == "1. Ler\n2. Resumir"
    for ruim in (
        "sem frontmatter",
        "---\nname: x\n---\n",
        "---\n- lista\n---\n",
        "---\nname: [\n---\n",
    ):
        with pytest.raises(ErroFerramenta):
            ler_skill_md(ruim)
    with pytest.raises(ErroFerramenta):
        montar_skill_md("x" * 81, "d", "c")


def test_playbook_e_catalogo() -> None:
    markdown = playbook_para_markdown(
        Playbook(
            quando_usar="Toda segunda",
            passos=["Abrir", "Somar"],
            como_conferir="Total bate",
            o_que_devolver="A planilha",
        )
    )
    assert "1. Abrir" in markdown and "aprovação explícita" in markdown
    assert instrucao_de_habilidades([]) is None
    assert "/Nome" in (instrucao_de_habilidades([("Resumo", "resume")]) or "")


def test_habilidade_forcada_e_mencoes() -> None:
    assert habilidade_forcada("/Resumo semanal\nfaz pra mim") == ("Resumo semanal", "faz pra mim")
    assert habilidade_forcada("Use a habilidade: Relatório") == ("Relatório", "")
    assert habilidade_forcada("oi /Resumo") is None
    assert mencoes_em_rotina("Rode @Resumo semanal e depois @todos") == ["Resumo semanal"]
    assert mencoes_em_rotina("use @Relatório Mensal, por favor", ["Relatório Mensal"]) == [
        "Relatório Mensal"
    ]


# ---------- trabalho parado ----------


def test_trabalho_parado() -> None:
    agora = AGORA
    esperando = t.EtapaParada("e", "aguardando_usuario", agora - timedelta(hours=5))
    assert t.acao_para(esperando, agora) is t.Acao.AVISAR
    avisado = t.EtapaParada("e", "aguardando_usuario", agora - timedelta(hours=5), ja_avisado=True)
    assert t.acao_para(avisado, agora) is t.Acao.NADA
    assert t.acao_para(t.EtapaParada("e", "pendente", agora - timedelta(hours=25)), agora) is (
        t.Acao.CANCELAR
    )
    rodando = t.EtapaParada("e", "executando", agora - timedelta(minutes=3))
    assert t.acao_para(rodando, agora) is t.Acao.NADA
    morta = t.EtapaParada("e", "executando", agora - timedelta(minutes=10))
    assert t.acao_para(morta, agora) is t.Acao.RETOMAR
    morta_de_novo = t.EtapaParada("e", "executando", agora - timedelta(minutes=10), retomadas=1)
    assert t.acao_para(morta_de_novo, agora) is t.Acao.FALHAR
    assert t.acao_para(t.EtapaParada("e", "concluida", agora - timedelta(days=9)), agora) is (
        t.Acao.NADA
    )
    assert "aprovação" in t.lembrete("Atlas", "aguardando_aprovacao")
    assert t.mensagem_de_status("pendente").startswith("Parei.")


# ---------- consultas SQL (compiladas no dialeto do PostgreSQL, sem banco) ----------


class _SessaoQueCompila:
    """Guarda o SQL de cada ``execute`` e devolve vazio."""

    def __init__(self) -> None:
        from sqlalchemy.dialects import postgresql

        self.dialeto = postgresql.dialect()
        self.sql: list[str] = []
        self.adicionados: list[object] = []

    async def execute(self, comando):  # type: ignore[no-untyped-def]
        self.sql.append(str(comando.compile(dialect=self.dialeto)))

        class _Vazio:
            rowcount = 1

            def all(self):  # type: ignore[no-untyped-def]
                return []

            def scalars(self):  # type: ignore[no-untyped-def]
                return self

            def __iter__(self):  # type: ignore[no-untyped-def]
                return iter([])

        return _Vazio()

    def add(self, objeto: object) -> None:
        self.adicionados.append(objeto)

    async def flush(self) -> None:
        return None


async def test_consultas_sql_filtram_pelo_dono() -> None:
    from app.ferramentas.historico import carregar_mensagens
    from app.memoria.servico import ArmazemMemoriasSQL
    from app.pendencias import listar_do_banco

    sessao = _SessaoQueCompila()
    usuario, agente = uuid4(), uuid4()
    armazem = ArmazemMemoriasSQL(sessao)  # type: ignore[arg-type]
    assert await armazem.buscar(usuario, agente, "relatórios curtos", 5) == []
    assert await armazem.buscar(usuario, agente, "a", 5) == []  # só palavras curtas: nem consulta
    assert await armazem.buscar(usuario, agente, "x", 5, vetor=[0.1] * 768) == []
    assert await armazem.apagar(usuario, uuid4())
    await armazem.listar(usuario, agente)
    await carregar_mensagens(sessao, usuario, uuid4())  # type: ignore[arg-type]
    await listar_do_banco(sessao, usuario, agente)  # type: ignore[arg-type]
    palavras, vetor, apagar, listar, mensagens, pendencias = sessao.sql
    assert "ORDER BY memorias.criada_em DESC" in listar
    assert "memorias.usuario_id = %(usuario_id_1)s" in palavras
    assert "memorias.apagada_em IS NULL" in palavras and "ILIKE" in palavras
    assert "<=>" in vetor and "::vector" in vetor
    assert apagar.startswith("UPDATE memorias SET apagada_em")
    assert "conversas.usuario_id" in mensagens and "mensagens.visivel IS true" in mensagens
    assert "pendencias.status IN" in pendencias
    await armazem.salvar(
        RegistroMemoria(id=uuid4(), usuario_id=usuario, agente_id=None, conteudo="x")
    )
    assert len(sessao.adicionados) == 1
    with pytest.raises(ValueError):
        await armazem.buscar(usuario, agente, "x", 5, vetor=[0.1] * 3)
