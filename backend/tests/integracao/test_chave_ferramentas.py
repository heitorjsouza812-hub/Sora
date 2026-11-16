"""Chave: ferramentas uma a uma, com banco real (Docker), contexto falso e nada de rede.

Foco: argumento inválido volta como texto para o modelo (``ErroFerramenta``), id inexistente ou
de OUTRA conta nunca vaza nem muda dado alheio, e o executor faz o que o esquema promete.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.banco import fabrica_sessoes
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.modelos.enumeracoes import AutorMensagem, TipoAgente
from app.modelos.tabelas import (
    Agente,
    Anexo,
    Cadeia,
    Conversa,
    Etapa,
    Habilidade,
    Mensagem,
)
from app.modelos.tabelas import Pendencia as LinhaPendencia
from tests.integracao.test_ferramentas_prumo import Cenario, cenario, servicos  # noqa: F401

pytestmark = pytest.mark.integracao


@dataclass
class Mundo:
    c: Cenario
    bot_a: UUID  # colega do mesmo usuário (com conversa)
    bot_b: UUID  # bot do OUTRO usuário
    conversa_b: UUID
    anexo_b: UUID  # anexo do outro usuário
    etapa_b: UUID  # etapa de uma cadeia do outro usuário

    def ctx(self, **extra) -> ContextoFerramenta:
        return (
            self.c.ctx()
            if not extra
            else ContextoFerramenta(
                usuario_id=self.c.usuario_id,
                agente_id=self.c.agente_id,
                conversa_id=self.c.conversa_id,
                **extra,
            )
        )

    def ctx_b(self) -> ContextoFerramenta:
        return ContextoFerramenta(
            usuario_id=self.c.outro_usuario_id, agente_id=self.bot_b, conversa_id=self.conversa_b
        )


@pytest.fixture
async def mundo(cenario: Cenario) -> AsyncIterator[Mundo]:  # noqa: F811
    async with fabrica_sessoes()() as s:
        a = Agente(usuario_id=cenario.usuario_id, tipo=TipoAgente.INDIVIDUAL, nome="Colega")
        b = Agente(usuario_id=cenario.outro_usuario_id, tipo=TipoAgente.INDIVIDUAL, nome="Alheio")
        s.add_all([a, b])
        await s.flush()
        conv_a = Conversa(usuario_id=cenario.usuario_id, agente_id=a.id)
        conv_b = Conversa(usuario_id=cenario.outro_usuario_id, agente_id=b.id)
        s.add_all([conv_a, conv_b])
        await s.flush()
        pedido_b = Mensagem(conversa_id=conv_b.id, autor=AutorMensagem.USUARIO, conteudo="segredo")
        s.add(pedido_b)
        await s.flush()
        anexo = Anexo(
            usuario_id=cenario.outro_usuario_id,
            nome="privado.txt",
            tipo="text/plain",
            tamanho=3,
            caminho=f"{cenario.outro_usuario_id}/privado.txt",
            origem="usuario",
        )
        cadeia = Cadeia(
            usuario_id=cenario.outro_usuario_id,
            conversa_id=conv_b.id,
            pedido_id=pedido_b.id,
            orcamento_tokens=1000,
        )
        s.add_all([anexo, cadeia])
        await s.flush()
        etapa = Etapa(
            cadeia_id=cadeia.id,
            ordem=1,
            agente_id=b.id,
            especialista="redator",
            tarefa="x",
            nivel="N2",
        )
        s.add(etapa)
        await s.commit()
        yield Mundo(cenario, a.id, b.id, conv_b.id, anexo.id, etapa.id)


async def _pend(usuario_id: UUID, agente_id: UUID, titulo: str = "do outro") -> UUID:
    async with fabrica_sessoes()() as s:
        p = LinhaPendencia(usuario_id=usuario_id, agente_id=agente_id, titulo=titulo, notas="")
        s.add(p)
        await s.commit()
        return p.id


# ------------------------------------------------------------------ pendências


async def test_pendencias_de_outro_usuario_ou_outro_bot_sao_invisiveis(mundo: Mundo) -> None:
    from app.ferramentas.pecas import (
        atualizar_pendencia,
        concluir_pendencia,
        listar_pendencias,
        remover_pendencia,
    )
    from app.pendencias import (
        AtualizarPendencia,
        ConcluirPendencia,
        ListarPendencias,
        RemoverPendencia,
    )

    alheia = await _pend(mundo.c.outro_usuario_id, mundo.bot_b, "SEGREDO-ALHEIO")
    do_colega = await _pend(mundo.c.usuario_id, mundo.bot_a, "do colega")
    for pid in (alheia, do_colega, uuid4()):
        with pytest.raises(ErroFerramenta, match="não encontrada"):
            await atualizar_pendencia(AtualizarPendencia(pendencia_id=pid, notas="x"), mundo.ctx())
        with pytest.raises(ErroFerramenta, match="não encontrada"):
            await concluir_pendencia(ConcluirPendencia(pendencia_id=pid), mundo.ctx())
        with pytest.raises(ErroFerramenta, match="não encontrada"):
            await remover_pendencia(RemoverPendencia(pendencia_id=pid), mundo.ctx())
    saida = await listar_pendencias(ListarPendencias(incluir_concluidas=True), mundo.ctx())
    assert "SEGREDO-ALHEIO" not in saida and "do colega" not in saida
    async with fabrica_sessoes()() as s:
        restantes = list(await s.scalars(select(LinhaPendencia.titulo)))
    assert {"SEGREDO-ALHEIO", "do colega"} <= set(restantes)  # nada foi apagado nem mudado


async def test_pendencia_so_com_espacos_vira_erro_legivel_e_nao_grava_titulo_vazio(
    mundo: Mundo,
) -> None:
    from app.ferramentas.pecas import adicionar_pendencia, atualizar_pendencia
    from app.pendencias import AdicionarPendencia, AtualizarPendencia

    with pytest.raises(ErroFerramenta):
        await adicionar_pendencia(AdicionarPendencia(titulo="   "), mundo.ctx())
    pid = await _pend(mundo.c.usuario_id, mundo.c.agente_id, "valida")
    with pytest.raises(ErroFerramenta):
        await atualizar_pendencia(AtualizarPendencia(pendencia_id=pid, titulo="   "), mundo.ctx())
    async with fabrica_sessoes()() as s:
        titulos = list(await s.scalars(select(LinhaPendencia.titulo)))
    assert "" not in titulos


async def test_pendencia_limite_de_abertas(mundo: Mundo) -> None:
    from app.ferramentas.pecas import adicionar_pendencia
    from app.pendencias import MAX_PENDENCIAS_ABERTAS, AdicionarPendencia

    async with fabrica_sessoes()() as s:
        s.add_all(
            LinhaPendencia(
                usuario_id=mundo.c.usuario_id, agente_id=mundo.c.agente_id, titulo=f"p{i}", notas=""
            )
            for i in range(MAX_PENDENCIAS_ABERTAS)
        )
        await s.commit()
    with pytest.raises(ErroFerramenta, match="Muitas pendências"):
        await adicionar_pendencia(AdicionarPendencia(titulo="mais uma"), mundo.ctx())


# ------------------------------------------------------------------ memória


async def test_memoria_escopo_do_usuario(mundo: Mundo) -> None:
    from app.ferramentas.pecas import buscar_memoria, esquecer_memoria, lembrar
    from app.memoria.servico import BuscarMemoria, EsquecerMemoria, Lembrar

    await lembrar(Lembrar(conteudo="o cliente alheio gosta de pistache"), mundo.ctx_b())
    dono = await lembrar(Lembrar(conteudo="minha cor favorita é verde"), mundo.ctx())
    meu_id = UUID(dono.split("id: ")[1].rstrip(")."))
    assert "pistache" not in await buscar_memoria(BuscarMemoria(consulta="pistache"), mundo.ctx())
    assert "verde" in await buscar_memoria(BuscarMemoria(consulta="cor verde"), mundo.ctx())
    # apagar a memória de outra conta: não acha e não apaga
    from app.modelos.tabelas import Memoria

    async with fabrica_sessoes()() as s:
        alheia = await s.scalar(
            select(Memoria.id).where(Memoria.usuario_id == mundo.c.outro_usuario_id)
        )
    assert "Não encontrei" in await esquecer_memoria(
        EsquecerMemoria(memoria_id=alheia), mundo.ctx()
    )
    assert "Não encontrei" in await esquecer_memoria(
        EsquecerMemoria(memoria_id=uuid4()), mundo.ctx()
    )
    async with fabrica_sessoes()() as s:
        assert await s.get(Memoria, alheia) is not None
    assert "apagada" in await esquecer_memoria(EsquecerMemoria(memoria_id=meu_id), mundo.ctx())


@pytest.mark.parametrize(
    "texto",
    ["minha senha é hunter2 e o token sk-abcdefghijklmnopqrstuvwxyz123456", "   "],
)
async def test_lembrar_recusa_segredo_e_vazio_com_erro_legivel(mundo: Mundo, texto: str) -> None:
    from app.ferramentas.pecas import lembrar
    from app.memoria.servico import Lembrar

    with pytest.raises(ErroFerramenta):
        await lembrar(Lembrar(conteudo=texto), mundo.ctx())


# ------------------------------------------------------------------ habilidades


async def test_habilidades_de_outro_usuario_e_do_sistema(mundo: Mundo) -> None:
    from app.ferramentas.pecas import (
        apagar_habilidade,
        atualizar_habilidade,
        criar_habilidade,
        ler_habilidade,
    )
    from app.habilidades import (
        ApagarHabilidade,
        AtualizarHabilidade,
        CriarHabilidade,
        LerHabilidade,
        montar_skill_md,
    )

    async with fabrica_sessoes()() as s:
        s.add_all(
            [
                Habilidade(
                    usuario_id=mundo.c.outro_usuario_id,
                    nome="Receita-Alheia",
                    descricao="d",
                    conteudo=montar_skill_md("Receita-Alheia", "d", "SEGREDO"),
                    origem="usuario",
                ),
                Habilidade(
                    usuario_id=mundo.c.usuario_id,
                    nome="Do-Sistema",
                    descricao="d",
                    conteudo=montar_skill_md("Do-Sistema", "d", "corpo"),
                    origem="sistema",
                ),
            ]
        )
        await s.commit()
    with pytest.raises(ErroFerramenta):
        await ler_habilidade(LerHabilidade(nome="Receita-Alheia"), mundo.ctx())
    with pytest.raises(ErroFerramenta):
        await atualizar_habilidade(
            AtualizarHabilidade(nome="Receita-Alheia", corpo="x"), mundo.ctx()
        )
    with pytest.raises(ErroFerramenta):
        await apagar_habilidade(ApagarHabilidade(nome="Receita-Alheia"), mundo.ctx())
    with pytest.raises(ErroFerramenta, match="sistema"):
        await atualizar_habilidade(AtualizarHabilidade(nome="Do-Sistema", corpo="x"), mundo.ctx())
    with pytest.raises(ErroFerramenta, match="sistema"):
        await apagar_habilidade(ApagarHabilidade(nome="Do-Sistema"), mundo.ctx())
    # criar com o mesmo nome de uma habilidade de OUTRO usuário é permitido (escopo por usuário)
    assert "criada" in await criar_habilidade(
        CriarHabilidade(nome="receita-alheia", descricao="d", corpo="meu passo a passo"),
        mundo.ctx(),
    )
    # nome só com espaços: erro legível, não exceção solta
    with pytest.raises(ErroFerramenta):
        await criar_habilidade(CriarHabilidade(nome="   ", descricao="d", corpo="x"), mundo.ctx())


# ------------------------------------------------------------------ enviar_para_agente


async def test_enviar_para_agente_so_para_colegas_do_mesmo_usuario(mundo: Mundo) -> None:
    from app.ferramentas.enviar_para_agente import EnviarParaAgente
    from app.ferramentas.pecas import enviar_para_agente

    for destino in (mundo.bot_b, uuid4(), mundo.c.agente_id):
        with pytest.raises(ErroFerramenta):
            await enviar_para_agente(EnviarParaAgente(agente_id=destino, texto="oi"), mundo.ctx())
    async with fabrica_sessoes()() as s:
        assert (
            await s.scalar(
                select(Mensagem.id).where(
                    Mensagem.conversa_id == mundo.conversa_b, Mensagem.agente_id.is_not(None)
                )
            )
            is None
        )


async def test_enviar_para_agente_responde_a_inexistente_vira_erro_legivel(mundo: Mundo) -> None:
    """``responde_a`` é uma chave estrangeira: um id inventado pelo modelo não pode estourar
    ``IntegrityError`` (que derrubaria o turno) nem apontar para mensagem de outra conta."""
    from app.ferramentas.enviar_para_agente import EnviarParaAgente
    from app.ferramentas.pecas import enviar_para_agente

    async with fabrica_sessoes()() as s:
        alheia = await s.scalar(select(Mensagem.id).where(Mensagem.conversa_id == mundo.conversa_b))
    for responde_a in (uuid4(), alheia):
        try:
            await enviar_para_agente(
                EnviarParaAgente(agente_id=mundo.bot_a, texto="oi", responde_a=responde_a),
                mundo.ctx(),
            )
        except ErroFerramenta:
            continue
        pytest.fail(f"aceitou responde_a={responde_a}")


async def test_enviar_para_agente_nao_promete_o_que_nao_faz(mundo: Mundo) -> None:
    """Se o esquema aceita ``anexos``, o executor entrega ou recusa; nunca ignora em silêncio."""
    from app.ferramentas.enviar_para_agente import EnviarParaAgente
    from app.ferramentas.pecas import enviar_para_agente

    with pytest.raises(ErroFerramenta):  # anexo de outra conta
        await enviar_para_agente(
            EnviarParaAgente(agente_id=mundo.bot_a, texto="veja", anexos=[mundo.anexo_b]),
            mundo.ctx(),
        )


# ------------------------------------------------------------------ anexos e arquivos


async def test_ler_anexo_de_outro_usuario_e_inexistente(mundo: Mundo) -> None:
    from app.ferramentas.ler_anexo import LerAnexo, ler_anexo

    for anexo in (mundo.anexo_b, uuid4()):
        with pytest.raises(ErroFerramenta, match="não encontrado"):
            await ler_anexo(LerAnexo(anexo_id=anexo), mundo.ctx())


async def test_escrever_arquivo_recusa_nomes_perigosos_e_grava_so_no_volume(mundo: Mundo) -> None:
    from pydantic import ValidationError

    from app.ferramentas.escrever_arquivo import EscreverArquivo, escrever_arquivo

    for nome in (
        "../x.md",
        "..\\x.md",
        "/etc/passwd",
        "C:\\x.md",
        "a/b.md",
        ".env",
        "con.txt",
        "NUL",
        "x.md.",
        " x.md",
        "a\x00b.md",
        "arq:fluxo",
        "x" * 200,
    ):
        with pytest.raises(ValidationError):
            EscreverArquivo(nome=nome, conteudo="x")
    saida = await escrever_arquivo(EscreverArquivo(nome="ok.md", conteudo="oi"), mundo.ctx())
    assert "anexo_id" in saida
    with pytest.raises(ErroFerramenta, match="grande"):
        await escrever_arquivo(EscreverArquivo(nome="g.md", conteudo="x" * 1_000_001), mundo.ctx())
    pasta = mundo.c.pasta
    achados = [p for p in pasta.rglob("*") if p.is_file()]
    assert achados and all(mundo.c.usuario_id.hex in p.as_posix().replace("-", "") for p in achados)


async def test_falar_recusa_anexo_e_resposta_de_outra_conta(mundo: Mundo) -> None:
    from app.ferramentas.falar import Falar, falar

    with pytest.raises(ErroFerramenta, match="anexo"):
        await falar(Falar(texto="oi", anexos=[mundo.anexo_b]), mundo.ctx())
    async with fabrica_sessoes()() as s:
        alheia = await s.scalar(select(Mensagem.id).where(Mensagem.conversa_id == mundo.conversa_b))
    with pytest.raises(ErroFerramenta, match="não existe"):
        await falar(Falar(texto="oi", responde_a=alheia), mundo.ctx())
    with pytest.raises(ErroFerramenta, match="vazia"):
        await falar(Falar(texto="   "), mundo.ctx())


# ------------------------------------------------------------------ especialistas


async def test_especialista_de_outro_usuario_e_inexistente(mundo: Mundo) -> None:
    from app.ferramentas.mensagem_especialista import MensagemEspecialista, mensagem_especialista
    from app.ferramentas.parar_especialista import PararEspecialista, parar_especialista
    from app.ferramentas.ver_especialista import VerEspecialista, ver_especialista

    for etapa in (mundo.etapa_b, uuid4()):
        with pytest.raises(ErroFerramenta, match="não encontrada"):
            await ver_especialista(VerEspecialista(etapa_id=etapa), mundo.ctx())
        with pytest.raises(ErroFerramenta, match="não encontrada"):
            await parar_especialista(PararEspecialista(etapa_id=etapa), mundo.ctx())
        with pytest.raises(ErroFerramenta, match="não encontrada"):
            await mensagem_especialista(
                MensagemEspecialista(etapa_id=etapa, texto="oi"), mundo.ctx()
            )
    async with fabrica_sessoes()() as s:
        assert (await s.get(Etapa, mundo.etapa_b)).status.value != "cancelada"


async def test_disparar_e_entregar_sem_cadeia(mundo: Mundo) -> None:
    from app.ferramentas.disparar_especialista import DispararEspecialista, disparar_especialista
    from app.ferramentas.entregar import Entregar, entregar
    from app.ferramentas.veredito import Veredito, veredito

    with pytest.raises(ErroFerramenta, match="cadeia"):
        await disparar_especialista(DispararEspecialista(papel="redator", tarefa="x"), mundo.ctx())
    with pytest.raises(ErroFerramenta, match="cadeia"):
        await entregar(Entregar(tipo="texto", titulo="t", resumo="r", conteudo="c"), mundo.ctx())
    with pytest.raises(ErroFerramenta, match="etapa"):
        await veredito(Veredito(aprovado=True, requisitos=[], motivo="ok"), mundo.ctx())
    # cadeia de outro usuário no contexto: "não encontrada", não executa
    alheio = ContextoFerramenta(
        usuario_id=mundo.c.usuario_id,
        agente_id=mundo.c.agente_id,
        conversa_id=mundo.c.conversa_id,
        cadeia_id=await _cadeia_de(mundo.etapa_b),
    )
    with pytest.raises(ErroFerramenta, match="Cadeia não encontrada"):
        await disparar_especialista(DispararEspecialista(papel="redator", tarefa="x"), alheio)
    with pytest.raises(ErroFerramenta, match="Cadeia não encontrada"):
        await entregar(Entregar(tipo="texto", titulo="t", resumo="r", conteudo="c"), alheio)


async def _cadeia_de(etapa_id: UUID) -> UUID:
    async with fabrica_sessoes()() as s:
        return (await s.get(Etapa, etapa_id)).cadeia_id


# ------------------------------------------------------------------ agenda


async def test_agenda_escopo_limites_e_valores_absurdos(mundo: Mundo) -> None:
    from pydantic import ValidationError

    from app.rotinas.agenda import Agendar, CancelarAgendamento
    from app.rotinas.ferramentas import agendar, cancelar_agendamento, listar_agendamentos

    ok = await agendar(Agendar(titulo="t", pedido="p", daqui_minutos=10), mundo.ctx())
    assert "Agendado" in ok
    rid = ok.split("id ")[1].split(")")[0]
    # o colega (outro bot do mesmo usuário) e o outro usuário não enxergam nem cancelam
    contexto_colega = ContextoFerramenta(
        usuario_id=mundo.c.usuario_id, agente_id=mundo.bot_a, conversa_id=mundo.c.conversa_id
    )
    assert (
        await listar_agendamentos(
            Agendar.__mro__
            and __import__("app.rotinas.agenda", fromlist=["x"]).ListarAgendamentos(),
            contexto_colega,
        )
        == []
    )
    for ctx in (contexto_colega, mundo.ctx_b()):
        with pytest.raises(ErroFerramenta, match="não encontrado"):
            await cancelar_agendamento(CancelarAgendamento(agendamento_id=rid), ctx)
    with pytest.raises(ErroFerramenta, match="inválido"):
        await cancelar_agendamento(CancelarAgendamento(agendamento_id="1"), mundo.ctx())
    # valores que o modelo erra
    for ruim in (
        dict(cron="* * * * *"),  # a cada minuto: cron só de 5 em 5
        dict(cron="isso não é cron"),
        dict(a_cada=30, unidade="minutos", cron="0 9 * * *"),  # dois jeitos
        dict(em="2001-01-01T10:00:00"),  # no passado
        dict(daqui_minutos=10**9),  # mais de 1 ano
    ):
        try:
            await agendar(Agendar(titulo="t", pedido="p", **ruim), mundo.ctx())
        except (ErroFerramenta, ValidationError):
            continue
        pytest.fail(f"aceitou {ruim}")
    # número absurdo estoura timedelta: precisa virar erro legível (ErroFerramenta/validação)
    for ruim in (
        dict(daqui_minutos=1e30),
        dict(daqui_segundos=1e30),
        dict(a_cada=1e30, unidade="dias"),
    ):
        try:
            await agendar(Agendar(titulo="t", pedido="p", **ruim), mundo.ctx())
        except (ErroFerramenta, ValidationError):
            continue
        except Exception as erro:
            pytest.fail(f"{ruim} -> {type(erro).__name__} (exceção solta derruba o turno)")
        pytest.fail(f"aceitou {ruim}")


async def test_agenda_limite_de_ativos_e_sem_supervisao(mundo: Mundo) -> None:
    from app.rotinas.agenda import MAX_AGENDAMENTOS_ATIVOS, Agendar, CancelarAgendamento
    from app.rotinas.ferramentas import agendar, cancelar_agendamento

    for i in range(MAX_AGENDAMENTOS_ATIVOS):
        await agendar(Agendar(titulo=f"t{i}", pedido="p", daqui_minutos=10 + i), mundo.ctx())
    with pytest.raises(ErroFerramenta, match="agendamentos ativos"):
        await agendar(Agendar(titulo="x", pedido="p", daqui_minutos=5), mundo.ctx())
    rotina = mundo.ctx(sem_supervisao=True)
    with pytest.raises(ErroFerramenta, match="sem supervisão"):
        await agendar(Agendar(titulo="x", pedido="p", daqui_minutos=5), rotina)
    with pytest.raises(ErroFerramenta, match="sem supervisão"):
        await cancelar_agendamento(CancelarAgendamento(agendamento_id=str(uuid4())), rotina)


# ------------------------------------------------------------------ servidor MCP


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8200/mcp",
        "http://localhost/mcp",
        "https://localhost/mcp",
        "https://10.0.0.5/mcp",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/mcp",
        "https://[::ffff:127.0.0.1]/mcp",
        "https://user:senha@exemplo.com/mcp",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "ftp://exemplo.com/x",
    ],
)
async def test_adicionar_servidor_mcp_recusa_endereco_interno_em_producao(url: str) -> None:
    from app.conectores.servidores import validar_servidor

    with pytest.raises(ErroFerramenta):
        await validar_servidor(url, ambiente_local=False)


async def test_adicionar_servidor_mcp_validacoes_do_esquema() -> None:
    from pydantic import ValidationError

    from app.conectores.servidores import AdicionarServidorMCP

    with pytest.raises(ValidationError):
        AdicionarServidorMCP(nome="x", url="https://ok.example/mcp", cabecalhos={"Host": "x"})
    with pytest.raises(ValidationError):
        AdicionarServidorMCP(nome="x", url="https://ok.example/mcp", cabecalhos={"X": "a\r\nB: c"})
    with pytest.raises(ValidationError):
        AdicionarServidorMCP(nome="x", url="https://ok.example/mcp", cabecalhos={"Cookie": "s=1"})


async def test_adicionar_servidor_mcp_sem_supervisao_e_sem_vazar_cabecalho(mundo: Mundo) -> None:
    from app.conectores.ferramenta import adicionar_servidor_mcp
    from app.conectores.servidores import AdicionarServidorMCP

    args = AdicionarServidorMCP(
        nome="x", url="https://ok.example/mcp", cabecalhos={"Authorization": "Bearer SEGREDO123"}
    )
    with pytest.raises(ErroFerramenta, match="sem supervisão"):
        await adicionar_servidor_mcp(args, mundo.ctx(sem_supervisao=True))


# ------------------------------------------------------------------ canais da empresa


async def test_consultar_cliente_e_conhecimento_exigem_autorizacao(mundo: Mundo) -> None:
    from app.canais_empresa.acesso import SEM_AUTORIZACAO
    from app.canais_empresa.ferramentas import (
        ConsultarCliente,
        ConsultarConhecimento,
        consultar_cliente,
        consultar_conhecimento,
    )

    with pytest.raises(ErroFerramenta, match="autorização") as erro:
        await consultar_cliente(ConsultarCliente(cliente="Maria"), mundo.ctx())
    assert str(erro.value) == SEM_AUTORIZACAO
    with pytest.raises(ErroFerramenta, match="autorização"):
        await consultar_conhecimento(ConsultarConhecimento(consulta="troca"), mundo.ctx())
    # bot de outra conta com o mesmo agente_id da autorização: a autorização é por usuário
    from app.canais_empresa import acesso

    async with fabrica_sessoes()() as s:
        await acesso.definir(s, mundo.c.usuario_id, "agente", mundo.c.agente_id, ["clientes"])
        await s.commit()
    outro_usuario_mesmo_agente = ContextoFerramenta(
        usuario_id=mundo.c.outro_usuario_id,
        agente_id=mundo.c.agente_id,
        conversa_id=mundo.conversa_b,
    )
    with pytest.raises(ErroFerramenta, match="autorização"):
        await consultar_cliente(ConsultarCliente(cliente="Maria"), outro_usuario_mesmo_agente)
    assert "Nenhum cliente" in await consultar_cliente(
        ConsultarCliente(cliente="Maria"), mundo.ctx()
    )


async def test_consultar_cliente_curinga_nao_lista_todos(mundo: Mundo) -> None:
    """``%`` e ``_`` digitados pelo modelo são texto, não curinga do SQL."""
    from app.canais_empresa import acesso
    from app.canais_empresa.ferramentas import ConsultarCliente, consultar_cliente
    from app.canais_empresa.tabelas import ConexaoCanalEmpresa, ContatoEmpresa

    async with fabrica_sessoes()() as s:
        await acesso.definir(s, mundo.c.usuario_id, "agente", mundo.c.agente_id, ["clientes"])
        conexao = ConexaoCanalEmpresa(
            usuario_id=mundo.c.usuario_id, canal="whatsapp", segredos=b"x"
        )
        s.add(conexao)
        await s.flush()
        for nome in ("Ana Silva", "Bruno Souza"):
            s.add(
                ContatoEmpresa(
                    usuario_id=mundo.c.usuario_id,
                    conexao_id=conexao.id,
                    canal="whatsapp",
                    id_externo=f"55119{uuid4().int % 10**8:08d}",
                    nome=nome,
                    papel="cliente",
                )
            )
        await s.commit()
    saida = await consultar_cliente(ConsultarCliente(cliente="%%"), mundo.ctx())
    assert "Ana" not in saida and "Bruno" not in saida
    saida = await consultar_cliente(ConsultarCliente(cliente="A_a"), mundo.ctx())
    assert "Ana" not in saida


# ------------------------------------------------------------------ propor_instrucoes


async def test_propor_instrucoes_so_muda_o_proprio_bot(mundo: Mundo) -> None:
    from app.ferramentas.pecas import propor_instrucoes
    from app.ferramentas.propor_instrucoes import ProporInstrucoes, preparar_proposta

    args = ProporInstrucoes(instrucoes="Seja breve.", motivo="pedido do usuário")
    with pytest.raises(ErroFerramenta, match="suas próprias"):
        preparar_proposta(args, mundo.ctx(), "", agente_alvo_id=str(mundo.bot_a))
    with pytest.raises(ErroFerramenta, match="igual"):
        preparar_proposta(args, mundo.ctx(), "Seja breve.")
    await propor_instrucoes(args, mundo.ctx())
    async with fabrica_sessoes()() as s:
        outro = await s.get(Agente, mundo.bot_a)
        alheio = await s.get(Agente, mundo.bot_b)
    assert outro.instrucoes != "Seja breve." and alheio.instrucoes != "Seja breve."
    # contexto de outra conta com o agente_id do bot: não encontra
    sequestro = ContextoFerramenta(
        usuario_id=mundo.c.outro_usuario_id,
        agente_id=mundo.c.agente_id,
        conversa_id=mundo.conversa_b,
    )
    with pytest.raises(ErroFerramenta, match="não encontrado"):
        await propor_instrucoes(args, sequestro)


# ------------------------------------------------------------------ histórico


async def test_historico_so_da_propria_conversa(mundo: Mundo) -> None:
    from app.ferramentas.historico import BuscarHistorico, LerHistorico
    from app.ferramentas.pecas import buscar_historico, ler_historico

    async with fabrica_sessoes()() as s:
        s.add(
            Mensagem(
                conversa_id=mundo.c.conversa_id,
                autor=AutorMensagem.USUARIO,
                conteudo="meu texto azul",
            )
        )
        await s.commit()
    achou = await buscar_historico(BuscarHistorico(consulta="azul"), mundo.ctx())
    assert "azul" in achou
    vazio = json.loads(await buscar_historico(BuscarHistorico(consulta="segredo"), mundo.ctx()))
    assert vazio["mensagens"] == []
    assert "segredo" not in await ler_historico(LerHistorico(mensagem_id=str(uuid4())), mundo.ctx())
    async with fabrica_sessoes()() as s:
        alheia = await s.scalar(select(Mensagem.id).where(Mensagem.conversa_id == mundo.conversa_b))
    assert "segredo" not in await ler_historico(LerHistorico(mensagem_id=str(alheia)), mundo.ctx())


async def test_catalogo_de_tarefas_so_lista_o_que_e_do_bot(mundo: Mundo) -> None:
    from app.ferramentas.catalogo_tarefas import CatalogoTarefas
    from app.ferramentas.pecas import catalogo_tarefas

    await _pend(mundo.c.outro_usuario_id, mundo.bot_b, "PENDENCIA-ALHEIA")
    saida = await catalogo_tarefas(CatalogoTarefas(), mundo.ctx())
    assert "PENDENCIA-ALHEIA" not in saida


# ------------------------------------------------------------------ canal, grupo e reações


async def test_ferramentas_de_canal_so_funcionam_dentro_de_uma_tarefa(mundo: Mundo) -> None:
    from app.canais_equipe.execucao import (
        canal_delegar,
        canal_historico,
        canal_resultado,
        canal_transferir,
    )
    from app.canais_equipe.ferramentas import (
        CanalDelegar,
        CanalHistorico,
        CanalResultado,
        CanalTransferir,
    )

    for chamada in (
        canal_historico(CanalHistorico(), mundo.ctx()),
        canal_delegar(CanalDelegar(agente_id=mundo.bot_a, instrucao="x"), mundo.ctx()),
        canal_transferir(CanalTransferir(agente_id=mundo.bot_a), mundo.ctx()),
        canal_resultado(CanalResultado(texto="pronto"), mundo.ctx()),
    ):
        with pytest.raises(ErroFerramenta, match="tarefa de canal"):
            await chamada


async def test_propor_grupo_com_grupo_existente_inexistente_ou_de_outro_usuario(
    mundo: Mundo,
) -> None:
    from app.ferramentas.propor_grupo import ProporGrupo, propor_grupo

    with pytest.raises(ErroFerramenta, match="único grupo"):
        await propor_grupo(
            ProporGrupo(pedido="faça isto", grupo_existente="Grupo que não existe"), mundo.ctx()
        )


async def test_reagir_so_em_mensagem_da_propria_conversa(mundo: Mundo) -> None:
    from app.correio.reacoes import ReagirMensagem
    from app.ferramentas.reagir import reagir

    async with fabrica_sessoes()() as s:
        alheia = await s.scalar(select(Mensagem.id).where(Mensagem.conversa_id == mundo.conversa_b))
    with pytest.raises(ErroFerramenta, match="não pode reagir"):
        await reagir(ReagirMensagem(mensagem_id=alheia, emoji="👍"), mundo.ctx())
    with pytest.raises(ErroFerramenta, match="não pode reagir"):
        await reagir(ReagirMensagem(mensagem_id=uuid4(), emoji="👍"), mundo.ctx())
