"""Etapa 6, Âncora-4: visão e imagem na resposta (10), memória editável (14), busca (17).

Parte pura: nada de banco nem de rede. A parte com PostgreSQL está em
``tests/integracao/test_etapa6_ancora4.py``.
"""

from __future__ import annotations

import base64
import time
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import fakeredis
import pytest

from app.agentes import visao
from app.agentes.visao import (
    AVISO_SEM_VISAO,
    MAX_BYTES_IMAGEM,
    MAX_IMAGENS,
    AnexoDaEntrada,
    montar_entrada,
)
from app.api.busca import dobrar, palavras_da_busca, trecho_destacado
from app.eventos.equipe import (
    MAX_TEXTO_MEMORIA_EVENTO,
    TIPOS_EVENTOS_EQUIPE,
    MemoriaCriadaEvento,
)
from app.ferramentas import saidas_do_turno
from app.ferramentas.base import ErroFerramenta
from app.memoria.servico import ArmazemMemoriasEmMemoria, ServicoMemoria

# ------------------------------------------------------------------ item 10: saídas do turno


@pytest.fixture
async def redis_saidas() -> AsyncIterator[fakeredis.FakeAsyncRedis]:
    cliente = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield cliente
    await cliente.aclose()


async def test_recolher_junta_explicitos_e_pendentes_sem_repetir_e_so_uma_vez(redis_saidas) -> None:
    usuario, agente = uuid4(), uuid4()
    a, b, c = uuid4(), uuid4(), uuid4()
    await saidas_do_turno.registrar(usuario, agente, a, redis=redis_saidas)
    await saidas_do_turno.registrar(usuario, agente, b, redis=redis_saidas)

    primeira = await saidas_do_turno.recolher(usuario, agente, [b, c], redis=redis_saidas)
    assert primeira == [b, c, a]  # o que o modelo indicou vem primeiro; ``b`` não repete
    # cada arquivo sai uma vez
    assert await saidas_do_turno.recolher(usuario, agente, redis=redis_saidas) == []


async def test_recolher_nao_mistura_agentes_nem_usuarios(redis_saidas) -> None:
    usuario, outro_usuario, agente, outro_agente = uuid4(), uuid4(), uuid4(), uuid4()
    anexo = uuid4()
    await saidas_do_turno.registrar(usuario, agente, anexo, redis=redis_saidas)
    assert await saidas_do_turno.recolher(usuario, outro_agente, redis=redis_saidas) == []
    assert await saidas_do_turno.recolher(outro_usuario, agente, redis=redis_saidas) == []
    assert await saidas_do_turno.recolher(usuario, agente, redis=redis_saidas) == [anexo]


async def test_saida_nao_recolhida_expira(monkeypatch: pytest.MonkeyPatch, redis_saidas) -> None:
    usuario, agente, anexo = uuid4(), uuid4(), uuid4()
    relogio = [1000.0]
    monkeypatch.setattr(time, "time", lambda: relogio[0])
    await saidas_do_turno.registrar(usuario, agente, anexo, redis=redis_saidas)
    relogio[0] += saidas_do_turno.VALIDADE_S + 1
    assert await saidas_do_turno.recolher(usuario, agente, redis=redis_saidas) == []


async def test_registro_guarda_no_maximo_dez_por_agente(
    monkeypatch: pytest.MonkeyPatch, redis_saidas
) -> None:
    usuario, agente = uuid4(), uuid4()
    relogio = [1000.0]
    monkeypatch.setattr(time, "time", lambda: relogio[0])
    ids = [uuid4() for _ in range(15)]
    for anexo in ids:
        relogio[0] += 1
        await saidas_do_turno.registrar(usuario, agente, anexo, redis=redis_saidas)
    assert await saidas_do_turno.recolher(usuario, agente, redis=redis_saidas) == ids[-10:]


async def test_pendente_sobrevive_ao_reinicio_do_worker(redis_saidas) -> None:
    """O registro mora no Redis: outro processo (ou o mesmo, reiniciado) ainda o recolhe, e o
    registro tem prazo no próprio Redis."""
    usuario, agente, anexo = uuid4(), uuid4(), uuid4()
    await saidas_do_turno.registrar(usuario, agente, anexo, redis=redis_saidas)
    chave = saidas_do_turno.chave_das_saidas(usuario, agente)
    assert 0 < await redis_saidas.ttl(chave) <= int(saidas_do_turno.VALIDADE_S)
    # "reinício": nada do processo é reaproveitado, só o Redis
    import importlib

    importlib.reload(saidas_do_turno)
    assert await saidas_do_turno.recolher(usuario, agente, redis=redis_saidas) == [anexo]


async def test_redis_fora_do_ar_nao_derruba_a_mensagem() -> None:
    class Quebrado:
        def pipeline(self, *a, **k):
            raise ConnectionError("sem Redis")

    explicito = uuid4()
    await saidas_do_turno.registrar(uuid4(), uuid4(), uuid4(), redis=Quebrado())  # só avisa no log
    assert await saidas_do_turno.recolher(uuid4(), uuid4(), [explicito], redis=Quebrado()) == [
        explicito
    ]


# ------------------------------------------------------------------ item 10: visão


def _anexo(nome: str, tipo: str, tamanho: int = 10) -> AnexoDaEntrada:
    return AnexoDaEntrada(uuid4(), nome, tipo, tamanho, f"u/{nome}")


async def _ler_png(anexo: AnexoDaEntrada) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + anexo.nome.encode()


async def test_sem_anexos_o_texto_passa_igual() -> None:
    entrada = await montar_entrada("oi", [], tem_visao=True, ler=_ler_png)
    assert entrada.conteudo == "oi" and entrada.avisos == []


async def test_arquivo_que_nao_e_imagem_vira_lista_com_id_para_ler_anexo() -> None:
    pdf = _anexo("<contrato>.pdf", "application/pdf")
    entrada = await montar_entrada("resuma", [pdf], tem_visao=True, ler=_ler_png)
    assert isinstance(entrada.conteudo, str)
    assert f"anexo_id: {pdf.id}" in entrada.conteudo
    assert "&lt;contrato&gt;.pdf" in entrada.conteudo  # nome escapado: não fecha a marca
    assert entrada.imagens_enviadas == 0 and entrada.avisos == []


async def test_imagem_com_modelo_de_visao_vai_como_image_url_em_base64() -> None:
    foto = _anexo("foto.png", "image/png")
    entrada = await montar_entrada("o que é isto?", [foto], tem_visao=True, ler=_ler_png)
    assert isinstance(entrada.conteudo, list)
    texto, imagem = entrada.conteudo
    assert texto["type"] == "text" and "o que é isto?" in texto["text"]
    assert f"anexo_id: {foto.id}" in texto["text"]
    assert imagem["type"] == "image_url"
    url = imagem["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == await _ler_png(foto)
    assert entrada.imagens_enviadas == 1 and entrada.avisos == []


async def test_imagem_sem_visao_avisa_o_usuario_e_o_bot_recebe_nota() -> None:
    foto = _anexo("foto.png", "image/png")
    lidos: list[UUID] = []

    async def ler(anexo: AnexoDaEntrada) -> bytes:
        lidos.append(anexo.id)
        return b"x"

    entrada = await montar_entrada("e agora?", [foto], tem_visao=False, ler=ler)
    assert lidos == []  # sem visão a imagem nem é lida do disco
    assert isinstance(entrada.conteudo, str) and "NÃO consegue ver" in entrada.conteudo
    assert "já foi avisado disso" in entrada.conteudo
    assert entrada.avisos == [AVISO_SEM_VISAO.format(quais="a imagem foto.png")]
    assert "Configurações → Modelos de IA" in entrada.avisos[0]


async def test_sem_visao_no_grupo_o_bot_e_quem_avisa() -> None:
    foto = _anexo("foto.png", "image/png")
    entrada = await montar_entrada(
        "olha", [foto], tem_visao=False, ler=_ler_png, usuario_avisado=False
    )
    assert entrada.avisos == []
    assert "avise o usuário" in entrada.conteudo


async def test_imagens_demais_ou_grandes_demais_ficam_de_fora_com_aviso() -> None:
    boas = [_anexo(f"f{i}.png", "image/png") for i in range(MAX_IMAGENS + 1)]
    entrada = await montar_entrada("veja", boas, tem_visao=True, ler=_ler_png)
    assert entrada.imagens_enviadas == MAX_IMAGENS
    assert entrada.avisos and f"f{MAX_IMAGENS}.png" in entrada.avisos[0]

    gigante = _anexo("gigante.png", "image/png", tamanho=MAX_BYTES_IMAGEM + 1)
    so_ela = await montar_entrada("veja", [gigante], tem_visao=True, ler=_ler_png)
    assert isinstance(so_ela.conteudo, str)  # nenhuma imagem seguiu
    assert so_ela.imagens_enviadas == 0
    assert "gigante.png" in so_ela.avisos[0] and "5 MB" in so_ela.avisos[0]


async def test_falha_ao_ler_o_arquivo_nao_derruba_o_turno() -> None:
    foto = _anexo("foto.png", "image/png")
    boa = _anexo("boa.png", "image/png")

    async def ler(anexo: AnexoDaEntrada) -> bytes:
        if anexo is foto:
            raise OSError("sumiu")
        return b"ok"

    entrada = await montar_entrada("veja", [foto, boa], tem_visao=True, ler=ler)
    assert entrada.imagens_enviadas == 1
    assert "foto.png" in entrada.avisos[0]


async def test_com_texto_troca_so_o_pedido_e_preserva_as_imagens() -> None:
    foto = _anexo("foto.png", "image/png")
    entrada = await montar_entrada("descreva", [foto], tem_visao=True, ler=_ler_png)
    nova = entrada.com_texto("descreva", "[habilidade] descreva")
    assert nova.conteudo[0]["text"].startswith("[habilidade] descreva")
    assert nova.conteudo[1] == entrada.conteudo[1]
    assert entrada.conteudo[0]["text"].startswith("descreva")  # a original não muda


def test_o_modulo_expoe_o_que_o_worker_usa() -> None:
    assert callable(visao.preparar_entrada) and callable(visao.modelos_com_visao)


# ------------------------------------------------------------------ item 14: memória editável


async def test_editar_memoria_troca_o_texto_e_trava() -> None:
    usuario, agente = uuid4(), uuid4()
    servico = ServicoMemoria(ArmazemMemoriasEmMemoria())
    registro = await servico.lembrar(usuario, agente, "Gosta de café", explicita=False)
    assert registro.origem == "sintese"
    editada = await servico.editar(usuario, registro.id, "  Gosta de café   sem açúcar ")
    assert editada is not None
    assert editada.id == registro.id and editada.conteudo == "Gosta de café sem açúcar"
    assert editada.origem == "explicita" and editada.travada is True


async def test_editar_memoria_de_outro_usuario_ou_apagada_nao_acha() -> None:
    dono, intruso = uuid4(), uuid4()
    servico = ServicoMemoria(ArmazemMemoriasEmMemoria())
    registro = await servico.lembrar(dono, None, "Mora em Curitiba")
    assert await servico.editar(intruso, registro.id, "Mora em Recife") is None
    assert (await servico.armazem.listar(dono, None))[0].conteudo == "Mora em Curitiba"
    assert await servico.esquecer(dono, registro.id)
    assert await servico.editar(dono, registro.id, "Mora em Recife") is None


async def test_editar_recusa_segredo_vazio_e_texto_repetido() -> None:
    usuario, agente = uuid4(), uuid4()
    servico = ServicoMemoria(ArmazemMemoriasEmMemoria())
    primeira = await servico.lembrar(usuario, agente, "Prefere respostas curtas")
    segunda = await servico.lembrar(usuario, agente, "Trabalha à noite")
    with pytest.raises(ErroFerramenta, match="senhas"):
        await servico.editar(usuario, segunda.id, "a chave é sk-abcdefghijklmnopqrstuvwxyz012345")
    with pytest.raises(ErroFerramenta, match="vazia"):
        await servico.editar(usuario, segunda.id, "   ")
    with pytest.raises(ErroFerramenta, match="Já existe"):
        await servico.editar(usuario, segunda.id, "prefere RESPOSTAS curtas")
    # editar para o próprio texto (mudando só a caixa) é permitido
    de_novo = await servico.editar(usuario, primeira.id, "Prefere respostas CURTAS")
    assert de_novo is not None and de_novo.conteudo == "Prefere respostas CURTAS"


def test_evento_memoria_criada_esta_entre_os_eventos_da_equipe() -> None:
    assert "memoria.criada" in TIPOS_EVENTOS_EQUIPE
    evento = MemoriaCriadaEvento(memoria_id=uuid4(), agente_id=uuid4(), texto="Gosta de café")
    dados = evento.model_dump(mode="json")
    assert dados["texto"] == "Gosta de café" and dados["conversa_id"] is None
    with pytest.raises(ValueError):
        MemoriaCriadaEvento(memoria_id=uuid4(), texto="x" * (MAX_TEXTO_MEMORIA_EVENTO + 1))


# ------------------------------------------------------------------ item 17: busca


def test_dobrar_tira_acento_e_caixa_sem_mudar_o_tamanho() -> None:
    texto = "AÇÃO Rápida, coração!"
    assert dobrar(texto) == "acao rapida, coracao!"
    assert len(dobrar(texto)) == len(texto)


def test_palavras_da_busca_dobra_tira_repetidas_e_limita() -> None:
    assert palavras_da_busca("  Café  CAFÉ coado ") == ["cafe", "coado"]
    assert len(palavras_da_busca("a b c d e f g h")) == 6


def test_trecho_destaca_a_palavra_sem_acento_e_sem_caixa() -> None:
    trecho, destaques = trecho_destacado("O orçamento da CAMPANHA ficou pronto", ["campanha"])
    assert trecho == "O orçamento da CAMPANHA ficou pronto"
    assert [trecho[i:f] for i, f in destaques] == ["CAMPANHA"]
    trecho, destaques = trecho_destacado("Preciso do orçamento hoje", ["orcamento"])
    assert [trecho[i:f] for i, f in destaques] == ["orçamento"]


def test_trecho_longo_corta_com_reticencias_e_mantem_o_destaque_dentro() -> None:
    texto = "início " * 60 + "a palavra rara aparece aqui " + "fim " * 80
    trecho, destaques = trecho_destacado(texto, ["rara"])
    assert trecho.startswith("…") and trecho.endswith("…")
    assert len(trecho) < len(texto)
    assert [trecho[i:f] for i, f in destaques] == ["rara"]


def test_trecho_junta_destaques_que_se_encostam_e_acha_todas_as_ocorrencias() -> None:
    trecho, destaques = trecho_destacado("café café, e mais café", ["cafe"])
    assert [trecho[i:f] for i, f in destaques] == ["café", "café", "café"]


def test_trecho_troca_quebra_de_linha_por_espaco() -> None:
    trecho, destaques = trecho_destacado("linha um\n\nlinha dois com ideia", ["ideia"])
    assert "\n" not in trecho
    assert [trecho[i:f] for i, f in destaques] == ["ideia"]


@pytest.mark.parametrize(
    "donos, global_max, mensagem", [("proprio", "10", "Sua conta"), ("outro", "2", "ocupados")]
)
async def test_limites_computadores(donos, global_max, mensagem, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.computador.virtual import ErroDocker, GerenteComputadoresDocker

    usuario = uuid4()
    dono = str(usuario) if donos == "proprio" else str(uuid4())
    cliente = SimpleNamespace(
        rodar=AsyncMock(
            return_value=SimpleNamespace(
                returncode=0, stdout=(dono + "\n" + dono + "\n").encode(), stderr=b""
            )
        )
    )
    monkeypatch.setenv("COMPUTADOR_MAX_GLOBAL", global_max)
    with pytest.raises(ErroDocker, match=mensagem):
        await GerenteComputadoresDocker(cliente)._conferir_limite(usuario)
