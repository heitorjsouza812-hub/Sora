"""C1/C2 (Farol): perfil padrão do bot e computador virtual por bot, sem Docker.

O computador de verdade (contêiner, rede, proxy) está em
``tests/integracao/test_computador_virtual.py``.
"""

from __future__ import annotations

import base64
from uuid import UUID, uuid4

import fakeredis.aioredis
import pytest
from pydantic import ValidationError

from app.computador.eventos import TelaComputadorEvento
from app.computador.interface import (
    AcaoComputador,
    AcaoResolvida,
    Alvo,
    ArquivoArea,
    Janela,
    Observacao,
    Tela,
    caminho_relativo,
    normalizar_tecla,
    parece_senha,
)
from app.computador.pc_usuario import RECUSA, ProvedorPcUsuario
from app.computador.servico import (
    CHAVE_CAPTURA,
    CHAVE_ESTADO,
    CHAVE_USO,
    SENHA,
    ServicoComputador,
    miniatura,
)
from app.computador.virtual import (
    ClienteDocker,
    GerenteComputadoresDocker,
    argumentos_do_container,
    comando_xdotool,
    ler_janelas,
)
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.revisor.politica import Politica, pode_sem_supervisao, politica_da_ferramenta


def _png(cor: tuple[int, int, int], tamanho: tuple[int, int] = (64, 40)) -> bytes:
    import io

    from PIL import Image

    saida = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(saida, format="PNG")
    return saida.getvalue()


# ---------- C1: navegador próprio por bot ----------


def test_bot_novo_nasce_com_navegador_proprio() -> None:
    from app.modelos.tabelas import Agente

    assert Agente.__table__.c.perfil_navegador.default.arg == "agente"
    # o padrão do banco não mudou: bots existentes mantêm a escolha que já têm
    assert Agente.__table__.c.perfil_navegador.server_default.arg == "compartilhado"


def test_saida_do_bot_diz_qual_navegador_usa() -> None:
    from app.api.agentes import _saida
    from app.modelos.enumeracoes import Movimento, TipoAgente
    from app.modelos.tabelas import Agente

    agente = Agente(
        id=uuid4(),
        usuario_id=uuid4(),
        tipo=TipoAgente.INDIVIDUAL,
        nome="Bia",
        funcao="Pesquisa",
        papel="Pesquisa",
        cor="#56A8FF",
        movimento=Movimento.GIRA,
        ferramentas=[],
        perfil_navegador="agente",
    )
    assert _saida(agente).perfil_navegador == "agente"
    agente.perfil_navegador = "nomeado"
    assert _saida(agente).perfil_navegador == "perfil"


def test_rota_do_navegador_aceita_escolher_o_perfil_do_agente() -> None:
    from app.api.navegador import _TIPO_NO_BANCO, EscolhaPerfilEntrada

    assert EscolhaPerfilEntrada(tipo="agente").tipo == "agente"
    assert _TIPO_NO_BANCO["agente"] == "agente"


def test_ferramentas_do_computador_podem_ser_ligadas_no_bot() -> None:
    from app.api.agentes import _validar_ferramentas
    from app.ferramentas.registro import ESQUEMAS

    nomes = ["computador_observar", "computador_agir", "computador_arquivos"]
    assert _validar_ferramentas(nomes) == nomes
    assert {*nomes, "computador_escrever_arquivo", "computador_desligar"} <= set(ESQUEMAS)


# ---------- política ----------


def test_politica_do_computador() -> None:
    assert politica_da_ferramenta("computador_agir") is Politica.REVISOR
    for nome in (
        "computador_observar",
        "computador_arquivos",
        "computador_escrever_arquivo",
        "computador_desligar",
    ):
        assert politica_da_ferramenta(nome) is Politica.LIVRE
    for nome in ("computador_observar", "computador_agir", "computador_arquivos"):
        assert not pode_sem_supervisao(nome)  # não aparece em rotina sem supervisão


# ---------- regras de entrada ----------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Enter", "Return"),
        ("ctrl+L", "ctrl+l"),
        ("Ctrl + Shift + T", "ctrl+shift+t"),
        ("alt+tab", "alt+Tab"),
        ("PageDown", "Page_Down"),
        ("F5", "F5"),
    ],
)
def test_teclas_permitidas(entrada: str, esperado: str) -> None:
    assert normalizar_tecla(entrada) == esperado


@pytest.mark.parametrize("entrada", ["super+l", "ctrl+alt+Delete", "a", "ctrl+;", "", "rm -rf"])
def test_teclas_recusadas(entrada: str) -> None:
    with pytest.raises(ErroFerramenta):
        normalizar_tecla(entrada)


@pytest.mark.parametrize(
    "texto", ["Cafe@2024", "Xk9#mPq2rT", "sk-proj-abcdefghijklmnopqrstuvwxyz123456", "Ab1!Ab1!"]
)
def test_parece_senha(texto: str) -> None:
    assert parece_senha(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "cafeteria em São Paulo",
        "https://exemplo.com.br/Pagina2",
        "maria@exemplo.com",
        "Relatorio",
        "echo ola > arquivos/x.txt",
    ],
)
def test_nao_parece_senha(texto: str) -> None:
    assert not parece_senha(texto)


@pytest.mark.parametrize("ruim", ["../x", "/etc/passwd", "a/../../b", "a\x00b", "x" * 400])
def test_caminho_fora_da_area_e_recusado(ruim: str) -> None:
    with pytest.raises(ErroFerramenta):
        caminho_relativo(ruim)


def test_caminho_relativo_valido() -> None:
    assert caminho_relativo("relatorios/maio.txt") == "relatorios/maio.txt"
    assert caminho_relativo(r"pasta\arquivo.csv") == "pasta/arquivo.csv"
    assert caminho_relativo("") == ""


def test_acao_coerente() -> None:
    with pytest.raises(ValidationError):
        AcaoComputador(tipo="clicar")
    with pytest.raises(ValidationError):
        AcaoComputador(tipo="clicar", x=10)
    with pytest.raises(ValidationError):
        AcaoComputador(tipo="arrastar", x=1, y=1)
    with pytest.raises(ValidationError):
        AcaoComputador(tipo="abrir")
    with pytest.raises(ValidationError):
        AcaoComputador(tipo="abrir", programa="bash")  # type: ignore[arg-type]
    assert AcaoComputador(tipo="clicar", ref="@c1:j1").ref == "@c1:j1"


# ---------- alvo virtual: argumentos ----------


def test_conteiner_nasce_travado_e_sem_nada_do_host() -> None:
    agente, usuario = uuid4(), uuid4()
    argv = argumentos_do_container(agente_id=agente, usuario_id=usuario, imagem="img:1")
    texto = " ".join(argv)
    for exigido in (
        "--read-only",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "--user 1000:1000",
        "--memory 1g",
        "--memory-swap 1g",
        "--cpus 1",
        "--pids-limit 512",
        "--ipc private",
        f"--network sora-pc-{agente.hex}",
        f"sora.usuario={usuario}",
    ):
        assert exigido in texto, exigido
    for proibido in ("--volume", "-v", "--mount", "--privileged", "--network host", "docker.sock"):
        assert proibido not in argv and proibido not in texto.split(), proibido
    assert argv[-1] == "img:1"


def test_xdotool_recebe_o_texto_como_argumento_unico() -> None:
    texto = "oi; rm -rf / && $(id)"
    argv = comando_xdotool(AcaoResolvida(AcaoComputador(tipo="digitar", texto=texto)))
    assert argv[:2] == ["xdotool", "type"] and argv[-2:] == ["--", texto]
    clique = comando_xdotool(AcaoResolvida(AcaoComputador(tipo="clicar", x=5, y=6), ponto=(5, 6)))
    assert clique == ["xdotool", "mousemove", "--sync", "5", "6", "click", "1"]
    rolar = comando_xdotool(
        AcaoResolvida(AcaoComputador(tipo="rolar", direcao="cima", quantidade=2), ponto=None)
    )
    assert rolar[-1] == "4" and "2" in rolar


def test_ler_janelas() -> None:
    saida = (
        "0x00400002  0 0    0    1280 800  computador Google - Chromium\n"
        "0x00600003  0 10   20   700  400  computador bot@computador: ~\n"
        "0x00600009  0 0    0    1    1    computador\n"
        "---\n6291459\n"
    )
    janelas = ler_janelas(saida)
    assert [j.titulo for j in janelas] == ["Google - Chromium", "bot@computador: ~"]
    assert [j.ativa for j in janelas] == [False, True]
    assert janelas[1].centro == (10 + 350, 20 + 200)


# ---------- serviço: observar → agir → conferir ----------


class _ComputadorFalso:
    alvo = Alvo.VIRTUAL

    def __init__(self) -> None:
        self.feitas: list[AcaoResolvida] = []
        self.cor = (10, 10, 10)
        self.arquivos: dict[str, bytes] = {}

    async def observar(self) -> Observacao:
        return Observacao(
            tela=Tela(_png(self.cor), 64, 40),
            janelas=[
                Janela("0x1", "Chromium", 0, 0, 64, 40, ativa=True),
                Janela("0x2", "Terminal", 4, 4, 20, 10),
            ],
        )

    async def agir(self, acao: AcaoResolvida) -> None:
        self.feitas.append(acao)
        if acao.acao.tipo != "rolar":
            self.cor = (self.cor[0] + 20, 0, 0)  # a tela muda

    async def listar_arquivos(self, pasta: str) -> list[ArquivoArea]:
        return [ArquivoArea(c, "arquivo", len(d)) for c, d in self.arquivos.items()]

    async def ler_arquivo(self, caminho: str, limite: int) -> bytes:
        return self.arquivos[caminho]

    async def escrever_arquivo(self, caminho: str, dados: bytes) -> None:
        self.arquivos[caminho] = dados


class _ProvedorFalso:
    def __init__(self) -> None:
        self.computadores: dict[UUID, _ComputadorFalso] = {}
        self.desligados: list[UUID] = []

    async def obter(self, usuario_id: UUID, agente_id: UUID) -> _ComputadorFalso:
        return self.computadores.setdefault(agente_id, _ComputadorFalso())

    async def desligar(self, agente_id: UUID) -> bool:
        self.desligados.append(agente_id)
        return self.computadores.pop(agente_id, None) is not None


@pytest.fixture
def servico(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.computador.servico.ESPERA_DEPOIS_DE_AGIR_S", 0)
    eventos: list[TelaComputadorEvento] = []

    async def publicar(evento: TelaComputadorEvento, _usuario: UUID) -> None:
        eventos.append(evento)

    class _Servico(ServicoComputador):  # sem __slots__: o teste pendura os falsos nele
        pass

    provedor = _ProvedorFalso()
    servico = _Servico(
        provedores={Alvo.VIRTUAL: provedor, Alvo.PC_USUARIO: ProvedorPcUsuario()},
        redis=fakeredis.aioredis.FakeRedis(),
        publicar=publicar,
    )
    servico.eventos = eventos  # type: ignore[attr-defined]
    servico.provedor = provedor  # type: ignore[attr-defined]
    return servico


def _ctx(**extra) -> ContextoFerramenta:
    return ContextoFerramenta(usuario_id=uuid4(), agente_id=uuid4(), conversa_id=uuid4(), **extra)


async def test_agir_sem_observar_e_recusado(servico) -> None:
    with pytest.raises(ErroFerramenta, match="Observe a tela"):
        await servico.agir(_ctx(), [AcaoComputador(tipo="clicar", x=1, y=1)])


async def test_ciclo_observar_agir_conferir(servico) -> None:
    ctx = _ctx()
    texto = await servico.observar(ctx)
    assert "@c1:j1" in texto and "64x40" in texto and "<dado_externo" in texto
    resultado = await servico.agir(
        ctx,
        [
            AcaoComputador(tipo="clicar", ref="@c1:j2"),
            AcaoComputador(tipo="digitar", texto="cafeteria"),
        ],
    )
    assert "2 de 2" in resultado and "a tela mudou" in resultado and "@c2:j1" in resultado
    feitas = servico.provedor.computadores[ctx.agente_id].feitas
    assert feitas[0].ponto == (14, 9) and feitas[0].janela.id_nativo == "0x2"
    # a tela ao vivo foi para o Redis e para o evento, sem o texto digitado
    guardada = await servico.redis.get(CHAVE_CAPTURA.format(agente_id=ctx.agente_id))
    assert base64.b64decode(guardada)[1:4] == b"PNG"
    assert await servico.redis.get(CHAVE_ESTADO.format(agente_id=ctx.agente_id))
    assert await servico.redis.hget(CHAVE_USO, str(ctx.agente_id))
    ultimo = servico.eventos[-1]
    assert ultimo.mudou is True and ultimo.miniatura.startswith("data:image/jpeg;base64,")
    assert "cafeteria" not in ultimo.model_dump_json()
    assert ultimo.acao == "Clicou em @c1:j2; Digitou 9 caracteres"


async def test_tela_que_nao_muda_e_avisada(servico) -> None:
    ctx = _ctx()
    await servico.observar(ctx)
    resultado = await servico.agir(ctx, [AcaoComputador(tipo="rolar")])
    assert "NÃO mudou" in resultado
    assert servico.eventos[-1].mudou is False


async def test_ref_velha_ponto_fora_e_senha_sao_recusados_antes_de_agir(servico) -> None:
    ctx = _ctx()
    await servico.observar(ctx)
    await servico.observar(ctx)  # leitura @c2
    for acao, motivo in (
        (AcaoComputador(tipo="clicar", ref="@c1:j1"), "leitura antiga"),
        (AcaoComputador(tipo="clicar", ref="@c2:j9"), "não existe"),
        (AcaoComputador(tipo="clicar", x=64, y=10), "fora da tela"),
        (AcaoComputador(tipo="digitar", texto="Cafe@2024"), "senhas"),
        (AcaoComputador(tipo="tecla", tecla="super+l"), "não permitid"),
    ):
        with pytest.raises(ErroFerramenta, match=motivo):
            await servico.agir(ctx, [AcaoComputador(tipo="clicar", x=1, y=1), acao])
    assert servico.provedor.computadores[ctx.agente_id].feitas == []  # nada foi feito
    assert SENHA.startswith("Não digito")


async def test_regras_de_uso(servico) -> None:
    with pytest.raises(ErroFerramenta, match="rotinas sem supervisão"):
        await servico.observar(_ctx(sem_supervisao=True))
    servico.virtual_ativo = lambda: False
    with pytest.raises(ErroFerramenta, match="desligado"):
        await servico.observar(_ctx())
    with pytest.raises(ErroFerramenta, match=RECUSA[:30]):
        await servico.observar(_ctx(), Alvo.PC_USUARIO)


async def test_arquivos_e_desligar(servico) -> None:
    ctx = _ctx()
    assert "Gravei notas.txt" in await servico.escrever(ctx, "notas.txt", "olá")
    assert "notas.txt" in await servico.arquivos(ctx, "listar", "")
    lido = await servico.arquivos(ctx, "ler", "notas.txt")
    assert "olá" in lido and "<dado_externo" in lido
    await servico.observar(ctx)
    assert "desligado" in await servico.desligar(ctx)
    assert not await servico.redis.get(CHAVE_CAPTURA.format(agente_id=ctx.agente_id))
    assert servico.eventos[-1].ligado is False
    assert (ctx.agente_id, Alvo.VIRTUAL) not in servico.leituras


async def test_dois_bots_tem_computadores_separados(servico) -> None:
    a, b = _ctx(), _ctx()
    await servico.observar(a)
    await servico.observar(b)
    await servico.agir(a, [AcaoComputador(tipo="clicar", x=1, y=1)])
    computadores = servico.provedor.computadores
    assert len(computadores[a.agente_id].feitas) == 1
    assert computadores[b.agente_id].feitas == []


def test_miniatura_cabe_no_evento() -> None:
    url = miniatura(_png((200, 30, 30), (1280, 800)))
    assert url is not None and url.startswith("data:image/jpeg;base64,")
    assert len(base64.b64decode(url.split(",", 1)[1])) < 64 * 1024


# ---------- gerente Docker sem Docker (cliente falso) ----------


class _ClienteFalso(ClienteDocker):
    def __init__(self, ps: str) -> None:
        self.ps = ps
        self.chamadas: list[tuple[str, ...]] = []

    async def rodar(self, *args: str, entrada=None, prazo=30):  # type: ignore[override]
        import subprocess

        self.chamadas.append(args)
        saida = self.ps.encode() if args[0] == "ps" else b"ok"
        return subprocess.CompletedProcess(args, 0, saida, b"")


async def test_desliga_so_os_ociosos() -> None:
    import time

    usado, parado, sem_registro = uuid4(), uuid4(), uuid4()
    ps = "\n".join(f"sora-pc-{a.hex}|{a}" for a in (usado, parado, sem_registro))
    cliente = _ClienteFalso(ps + "\nsora-pc-proxy|\n")
    gerente = GerenteComputadoresDocker(cliente)
    agora = time.time()
    desligados = await gerente.desligar_ociosos({usado: agora, parado: agora - 3600}, 900)
    assert set(desligados) == {parado, sem_registro}
    removidos = {c[2] for c in cliente.chamadas if c[:2] == ("rm", "-f")}
    assert removidos == {f"sora-pc-{parado.hex}", f"sora-pc-{sem_registro.hex}"}


async def test_ferramenta_montada_pelo_registro_recusa_com_sandbox_desligado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.computador import ferramentas
    from app.core.config import obter_configuracao
    from app.ferramentas.registro import criar_ferramentas

    monkeypatch.setenv("SANDBOX_PROVEDOR", "nenhum")
    obter_configuracao.cache_clear()
    ferramentas.configurar(None)
    try:
        (observar, agir) = criar_ferramentas(["computador_observar", "computador_agir"], _ctx())
        assert observar.name == "computador_observar" and agir.name == "computador_agir"
        resposta = await observar.ainvoke({})
        assert resposta == "Erro: O computador virtual está desligado neste servidor."
        resposta = await agir.ainvoke({"acoes": [{"tipo": "tecla", "tecla": "Enter"}]})
        assert resposta == "Erro: O computador virtual está desligado neste servidor."
    finally:
        ferramentas.configurar(None)
        obter_configuracao.cache_clear()
