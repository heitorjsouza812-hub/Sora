"""Ferramentas de leitura e criação (Prumo) com Postgres e Redis reais (Docker); sem Docker, pula.

Cobre ``falar``, ``escrever_arquivo``, ``ler_anexo``, ``gerar_imagem`` (modelo falso, sem
rede) e ``buscar_web`` (provedor de busca falso).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from openpyxl import Workbook
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.banco import fabrica_sessoes
from app.core.config import obter_configuracao
from app.eventos.streams import canal_conversa
from app.ferramentas import ambiente
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta
from app.ferramentas.buscar_web import BuscarWeb, buscar_web
from app.ferramentas.escrever_arquivo import EscreverArquivo, escrever_arquivo
from app.ferramentas.falar import Falar, falar
from app.ferramentas.gerar_imagem import GerarImagem, gerar_imagem
from app.ferramentas.ler_anexo import LerAnexo, ler_anexo
from app.modelos.enumeracoes import AutorMensagem, TipoAgente, TipoProvedor
from app.modelos.tabelas import (
    Agente,
    Anexo,
    ChamadaModelo,
    Conversa,
    Mensagem,
    ModeloDisponivel,
    Provedor,
    Usuario,
)

pytestmark = pytest.mark.integracao
RAIZ = Path(__file__).resolve().parents[2]


class Cenario:
    redis: Redis
    usuario_id: UUID
    agente_id: UUID
    conversa_id: UUID
    outro_usuario_id: UUID
    pasta: Path

    def ctx(self, usuario_id: UUID | None = None) -> ContextoFerramenta:
        return ContextoFerramenta(
            usuario_id=usuario_id or self.usuario_id,
            agente_id=self.agente_id,
            conversa_id=self.conversa_id,
        )


@pytest.fixture(scope="module")
def servicos():
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    with (
        PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg") as postgres,
        RedisContainer("redis:7") as redis,
    ):
        yield (
            postgres.get_connection_url(),
            f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0",
        )


@pytest.fixture
async def cenario(servicos, tmp_path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Cenario]:
    url_pg, url_redis = servicos
    monkeypatch.setenv("AMBIENTE", "teste")
    monkeypatch.setenv("DATABASE_URL", url_pg)
    monkeypatch.setenv("REDIS_URL", url_redis)
    monkeypatch.setenv("SORA_MODELO_FALSO", "1")
    monkeypatch.setenv("BUSCA_PROVEDOR", "falso")
    monkeypatch.setenv("PASTA_ARQUIVOS", str(tmp_path))
    obter_configuracao.cache_clear()
    fabrica_sessoes.cache_clear()
    ambiente.redis_dos_eventos.cache_clear()

    alembic = Config(str(RAIZ / "alembic.ini"))
    alembic.set_main_option("script_location", str(RAIZ / "migrations"))
    await asyncio.to_thread(command.upgrade, alembic, "head")

    c = Cenario()
    c.pasta = tmp_path
    c.redis = Redis.from_url(url_redis, decode_responses=True)
    await c.redis.flushdb()
    motor = create_async_engine(url_pg)
    async with async_sessionmaker(motor, expire_on_commit=False)() as sessao:
        usuario = Usuario(email=f"{uuid4()}@exemplo.com", nome="Ana", senha_hash="x")
        outro = Usuario(email=f"{uuid4()}@exemplo.com", nome="Bia", senha_hash="x")
        sessao.add_all([usuario, outro])
        await sessao.flush()
        sora = Agente(usuario_id=usuario.id, tipo=TipoAgente.SORA, nome="Sora")
        sessao.add(sora)
        await sessao.flush()
        conversa = Conversa(usuario_id=usuario.id, agente_id=sora.id)
        sessao.add(conversa)
        await sessao.commit()
        c.usuario_id, c.outro_usuario_id = usuario.id, outro.id
        c.agente_id, c.conversa_id = sora.id, conversa.id
    yield c
    await c.redis.aclose()
    await ambiente.redis_dos_eventos().aclose()
    await motor.dispose()
    ambiente.redis_dos_eventos.cache_clear()
    fabrica_sessoes.cache_clear()
    obter_configuracao.cache_clear()


async def _anexo(c: Cenario, usuario_id: UUID) -> Anexo:
    async with fabrica_sessoes()() as sessao:
        return await sessao.scalar(select(Anexo).where(Anexo.usuario_id == usuario_id))


async def test_falar_grava_mensagem_e_emite_eventos(cenario: Cenario) -> None:
    texto = "Olá! " * 200  # 1.000 caracteres: três deltas
    await falar(Falar(texto=texto), cenario.ctx())

    async with fabrica_sessoes()() as sessao:
        mensagem = await sessao.scalar(
            select(Mensagem).where(Mensagem.conversa_id == cenario.conversa_id)
        )
    assert mensagem.autor is AutorMensagem.SORA
    assert mensagem.conteudo == texto.strip()
    assert mensagem.visivel is True

    itens = await cenario.redis.xrange(canal_conversa(cenario.conversa_id))
    assert [campos["event"] for _, campos in itens] == [
        "mensagem.inicio",
        "mensagem.delta",
        "mensagem.delta",
        "mensagem.delta",
        "mensagem.fim",
    ]


async def test_falar_recusa_anexo_de_outro_usuario(cenario: Cenario) -> None:
    await escrever_arquivo(
        EscreverArquivo(nome="a.md", conteudo="x"), cenario.ctx(cenario.outro_usuario_id)
    )
    anexo = await _anexo(cenario, cenario.outro_usuario_id)
    with pytest.raises(ErroFerramenta):
        await falar(Falar(texto="oi", anexos=[anexo.id]), cenario.ctx())


async def test_escrever_e_ler_anexo(cenario: Cenario) -> None:
    resposta = await escrever_arquivo(
        EscreverArquivo(nome="relatorio.md", conteudo="# Café\n\nPlano da campanha."), cenario.ctx()
    )
    anexo = await _anexo(cenario, cenario.usuario_id)
    assert str(anexo.id) in resposta
    assert anexo.origem == "especialista"
    assert (cenario.pasta / anexo.caminho).is_file()
    assert anexo.caminho.startswith(f"{cenario.usuario_id}/cadeias/")

    lido = await ler_anexo(LerAnexo(anexo_id=anexo.id), cenario.ctx())
    assert "Plano da campanha." in lido


async def test_ler_anexo_de_outro_usuario_e_nao_encontrado(cenario: Cenario) -> None:
    await escrever_arquivo(EscreverArquivo(nome="segredo.md", conteudo="x"), cenario.ctx())
    anexo = await _anexo(cenario, cenario.usuario_id)
    with pytest.raises(ErroFerramenta, match="não encontrado"):
        await ler_anexo(LerAnexo(anexo_id=anexo.id), cenario.ctx(cenario.outro_usuario_id))


async def test_ler_anexo_com_caminho_adulterado_no_banco(cenario: Cenario) -> None:
    await escrever_arquivo(EscreverArquivo(nome="a.md", conteudo="x"), cenario.ctx())
    async with fabrica_sessoes()() as sessao:
        anexo = await sessao.scalar(select(Anexo).where(Anexo.usuario_id == cenario.usuario_id))
        anexo.caminho = "../../etc/passwd"
        await sessao.commit()
        anexo_id = anexo.id
    with pytest.raises(ErroFerramenta, match="não encontrado"):
        await ler_anexo(LerAnexo(anexo_id=anexo_id), cenario.ctx())


async def test_ler_anexo_planilha(cenario: Cenario) -> None:
    pasta = Workbook()
    pasta.active.title = "Posts"
    pasta.active.append(["dia", "tema"])
    pasta.active.append([1, "latte art"])
    buffer = BytesIO()
    pasta.save(buffer)
    destino = cenario.pasta / "planilha.xlsx"
    destino.write_bytes(buffer.getvalue())
    async with fabrica_sessoes()() as sessao:
        anexo = Anexo(
            usuario_id=cenario.usuario_id,
            nome="planilha.xlsx",
            tipo="application/octet-stream",
            tamanho=destino.stat().st_size,
            caminho="planilha.xlsx",
        )
        sessao.add(anexo)
        await sessao.commit()
        anexo_id = anexo.id
    lido = await ler_anexo(LerAnexo(anexo_id=anexo_id), cenario.ctx())
    assert "## Posts" in lido and "1 | latte art" in lido


async def test_gerar_imagem_sem_modelo_de_imagem(cenario: Cenario) -> None:
    with pytest.raises(ErroFerramenta, match="modelo de imagem"):
        await gerar_imagem(GerarImagem(descricao="uma xícara"), cenario.ctx())


async def test_gerar_imagem_com_modelo_falso(cenario: Cenario) -> None:
    from datetime import UTC, datetime

    nome_modelo = "openai/gpt-image-1"
    async with fabrica_sessoes()() as sessao:
        provedor = Provedor(
            usuario_id=cenario.usuario_id, tipo=TipoProvedor.OPENAI, validado_em=datetime.now(UTC)
        )
        sessao.add(provedor)
        await sessao.flush()
        sessao.add(
            ModeloDisponivel(
                provedor_id=provedor.id,
                modelo=nome_modelo,
                nivel="N2",
                capacidades=["imagem"],
                contexto=8000,
            )
        )
        await sessao.commit()

    resposta = await gerar_imagem(GerarImagem(descricao="uma xícara", quantidade=2), cenario.ctx())
    assert "2 imagem" in resposta
    async with fabrica_sessoes()() as sessao:
        anexos = (
            await sessao.scalars(select(Anexo).where(Anexo.usuario_id == cenario.usuario_id))
        ).all()
        chamadas = (await sessao.scalars(select(ChamadaModelo))).all()
    assert len(anexos) == 2
    for anexo in anexos:
        assert anexo.tipo == "image/png" and anexo.origem == "especialista"
        assert (cenario.pasta / anexo.caminho).read_bytes().startswith(b"\x89PNG")
    assert len(chamadas) == 2


async def test_buscar_web_com_provedor_falso(cenario: Cenario) -> None:
    resposta = await buscar_web(
        BuscarWeb(consulta="cafeterias no bairro", max_resultados=3), cenario.ctx()
    )
    assert resposta.startswith("1. ")
    assert "http" in resposta
