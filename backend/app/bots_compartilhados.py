"""Compartilhar, exportar e importar bot (Onda 3, item 16; ideia vista no OpenBot, escrita do zero).

O que sai de um bot é o **retrato**: nome, função, cor, movimento, instruções, ferramentas e, se o
dono escolher, as rotinas dele e algumas habilidades. Nunca saem arquivos, memória, conversas,
chaves, conectores nem a conta do dono. O mesmo retrato serve ao link público, ao ``.zip`` e à
importação.

Na importação, tudo é tratado como vindo de fora:

- cada campo tem teto e o ``.zip`` tem teto de tamanho (também descompactado);
- só entram ferramentas da lista ``FERRAMENTAS_IMPORTAVEIS`` (sem computador nem dados de
  clientes, que o usuário liga à parte);
- rotinas chegam **pausadas** (o usuário liga quando quiser) e com agenda conferida;
- o nome ganha um número se já existir na conta.
"""

from __future__ import annotations

import html
import io
import json
import secrets
import zipfile
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.ferramentas.base import ErroFerramenta
from app.habilidades import MAX_CONTEUDO, MAX_DESCRICAO, MAX_NOME
from app.modelos.esquemas import CURTO_MAX
from app.rotinas.agenda import MAX_PEDIDO

FORMATO = "sora-bot"
VERSAO = 1
MAX_NOME_BOT = 60
MAX_FUNCAO = 80
MAX_INSTRUCOES = 8_000
MAX_ROTINAS = 10
MAX_HABILIDADES = 10
MAX_ZIP = 1024 * 1024
MAX_DESCOMPACTADO = 2 * 1024 * 1024
INTERVALO_MINIMO_S = 60
INTERVALO_MAXIMO_S = 366 * 24 * 3600
ARQUIVO_BOT = "bot.json"

Movimento = Literal["gira", "vibracao", "espiral", "ondas"]


class RotinaCompartilhada(BaseModel):
    titulo: str = Field(min_length=1, max_length=120)
    pedido: str = Field(min_length=1, max_length=MAX_PEDIDO)
    tipo: Literal["cron", "intervalo"]
    expressao: str = Field(min_length=1, max_length=100)
    fuso: str = Field(default="America/Sao_Paulo", max_length=64)
    silencioso: bool = False


class HabilidadeCompartilhada(BaseModel):
    nome: str = Field(min_length=1, max_length=MAX_NOME)
    descricao: str = Field(min_length=1, max_length=MAX_DESCRICAO)
    corpo: str = Field(min_length=1, max_length=MAX_CONTEUDO)


class BotRetrato(BaseModel):
    nome: str = Field(min_length=1, max_length=MAX_NOME_BOT)
    funcao: str = Field(default="", max_length=MAX_FUNCAO)
    papel: str = Field(default="", max_length=CURTO_MAX)
    cor: str = Field(default="#46E8A8", max_length=7)
    movimento: Movimento = "gira"
    instrucoes: str = Field(default="", max_length=MAX_INSTRUCOES)
    ferramentas: list[str] = Field(default_factory=list, max_length=50)
    rotinas: list[RotinaCompartilhada] = Field(default_factory=list, max_length=MAX_ROTINAS)
    habilidades: list[HabilidadeCompartilhada] = Field(
        default_factory=list, max_length=MAX_HABILIDADES
    )


class Pacote(BaseModel):
    formato: Literal["sora-bot"] = FORMATO
    versao: Literal[1] = VERSAO
    exportado_em: datetime | None = None
    bot: BotRetrato


def gerar_codigo() -> str:
    """Código do link: 16 caracteres aleatórios (96 bits), seguros para URL."""
    return secrets.token_urlsafe(12)


def codigo_valido(codigo: str) -> bool:
    return 8 <= len(codigo) <= 40 and all(c.isalnum() or c in "-_" for c in codigo)


def validar_agenda(rotina: RotinaCompartilhada) -> RotinaCompartilhada:
    """Confere a agenda de uma rotina vinda de fora; ``ErroFerramenta`` se não valer."""
    from app.rotinas.agenda import (
        INTERVALO_MINIMO_CRON,
        fuso_valido,
        intervalo_do_cron,
        proxima_cron,
    )

    fuso = fuso_valido(rotina.fuso)
    if rotina.tipo == "cron":
        proxima_cron(rotina.expressao, datetime.now(UTC), fuso)
        if intervalo_do_cron(rotina.expressao, fuso) < INTERVALO_MINIMO_CRON:
            raise ErroFerramenta("Rotina com intervalo curto demais.")
    else:
        try:
            segundos = int(rotina.expressao)
        except ValueError as erro:
            raise ErroFerramenta("Intervalo inválido.") from erro
        if not INTERVALO_MINIMO_S <= segundos <= INTERVALO_MAXIMO_S:
            raise ErroFerramenta("Intervalo fora do permitido.")
    return rotina.model_copy(update={"fuso": fuso})


# ---------------------------------------------------------------- .zip


def escrever_zip(retrato: BotRetrato) -> bytes:
    pacote = Pacote(exportado_em=datetime.now(UTC), bot=retrato)
    leia_me = (
        f"Bot {retrato.nome}, exportado da Sora.\n\n"
        "Para usar: na Sora, abra Bots → Importar bot e escolha este arquivo. As rotinas chegam\n"
        "pausadas; ligue as que quiser.\n\n"
        "Este arquivo não tem conversas, memória, arquivos nem chaves.\n"
    )
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", compression=zipfile.ZIP_DEFLATED) as arquivo:
        arquivo.writestr(ARQUIVO_BOT, pacote.model_dump_json(indent=2))
        arquivo.writestr("LEIA-ME.txt", leia_me)
    return saida.getvalue()


def ler_zip(dados: bytes) -> BotRetrato:
    """Lê o ``bot.json`` de um ``.zip`` exportado pela Sora, com tetos contra arquivo malicioso."""
    if len(dados) > MAX_ZIP:
        raise ErroFerramenta("O arquivo passa de 1 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as arquivo:
            info = next((i for i in arquivo.infolist() if i.filename == ARQUIVO_BOT), None)
            if info is None:
                raise ErroFerramenta("Este .zip não é um bot exportado da Sora.")
            if info.file_size > MAX_DESCOMPACTADO:
                raise ErroFerramenta("O bot do arquivo é grande demais.")
            with arquivo.open(info) as entrada:
                bruto = entrada.read(MAX_DESCOMPACTADO + 1)
    except zipfile.BadZipFile as erro:
        raise ErroFerramenta("Não consegui abrir o arquivo: ele não é um .zip.") from erro
    if len(bruto) > MAX_DESCOMPACTADO:
        raise ErroFerramenta("O bot do arquivo é grande demais.")
    try:
        return Pacote.model_validate(json.loads(bruto.decode("utf-8"))).bot
    except (ValueError, ValidationError) as erro:
        raise ErroFerramenta("O arquivo não tem um bot válido da Sora.") from erro


def nome_do_arquivo(nome: str) -> str:
    base = "".join(c if c.isalnum() else "-" for c in nome.lower()).strip("-") or "bot"
    return f"{base[:40]}.sora-bot.zip"


# ---------------------------------------------------------------- prévia


def pagina_de_previa(retrato: BotRetrato, codigo: str, base_url: str) -> str:
    """HTML do ``/b/<código>``: as marcas Open Graph para WhatsApp e redes sociais, e o caminho
    para a página do app (refresh em meta: o CSP do site não deixa script em linha)."""
    base = base_url.rstrip("/")
    destino = f"/compartilhado/{codigo}"
    titulo = html.escape(f"{retrato.nome} · bot feito na Sora")
    descricao = html.escape(retrato.funcao or "Um bot de IA para usar na Sora.")
    imagem = html.escape(f"{base}/v1/publico/bots/{codigo}/imagem.png")
    endereco = html.escape(f"{base}/b/{codigo}")
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        f"<title>{titulo}</title>"
        f'<meta name="description" content="{descricao}">'
        f'<meta property="og:title" content="{titulo}">'
        f'<meta property="og:description" content="{descricao}">'
        f'<meta property="og:image" content="{imagem}">'
        '<meta property="og:image:width" content="1200">'
        '<meta property="og:image:height" content="630">'
        f'<meta property="og:url" content="{endereco}">'
        '<meta property="og:type" content="website">'
        '<meta property="og:site_name" content="Sora">'
        '<meta name="twitter:card" content="summary_large_image">'
        f'<meta http-equiv="refresh" content="0; url={html.escape(destino)}">'
        '<meta name="robots" content="noindex">'
        '</head><body style="background:#050608;color:#F2F5FB;font-family:sans-serif">'
        f'<p><a href="{html.escape(destino)}" style="color:#F2F5FB">'
        f"Abrir {html.escape(retrato.nome)} na Sora</a></p>"
        "</body></html>"
    )


def _cor_rgb(cor: str) -> tuple[int, int, int]:
    try:
        return int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16)
    except ValueError:
        return 70, 232, 168


def imagem_de_previa(retrato: BotRetrato) -> bytes:
    """PNG 1200 x 630 com o bot: pontos de luz na cor dele, nome e função (fundo da Sora)."""
    import math

    from PIL import Image, ImageDraw, ImageFont

    largura, altura = 1200, 630
    imagem = Image.new("RGB", (largura, altura), (5, 6, 8))
    desenho = ImageDraw.Draw(imagem)
    r, g, b = _cor_rgb(retrato.cor)
    centro_x, centro_y, raio = 300, 315, 150
    # esfera de pontos (o mascote é feito só de pontos de luz)
    for anel in range(1, 13):
        fi = math.pi * anel / 13
        pontos = max(6, int(28 * math.sin(fi)))
        for k in range(pontos):
            teta = 2 * math.pi * k / pontos + anel * 0.3
            x = centro_x + raio * math.sin(fi) * math.cos(teta)
            y = centro_y + raio * math.cos(fi) * 0.92
            brilho = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(fi) * math.cos(teta))
            tamanho = 2 + 3 * brilho
            cor = (int(r * brilho), int(g * brilho), int(b * brilho))
            desenho.ellipse((x - tamanho, y - tamanho, x + tamanho, y + tamanho), fill=cor)
    for olho_x in (centro_x - 46, centro_x - 6):
        desenho.ellipse((olho_x - 9, centro_y - 26, olho_x + 9, centro_y + 6), fill=(226, 236, 255))
    fonte_nome = ImageFont.load_default(size=72)
    fonte_funcao = ImageFont.load_default(size=34)
    fonte_rodape = ImageFont.load_default(size=26)
    desenho.text((540, 220), retrato.nome[:24], font=fonte_nome, fill=(242, 245, 251))
    funcao = retrato.funcao or "Bot de IA"
    linhas, linha = [], ""
    for palavra in funcao.split():
        tentativa = f"{linha} {palavra}".strip()
        if desenho.textlength(tentativa, font=fonte_funcao) > 600 and linha:
            linhas.append(linha)
            linha = palavra
        else:
            linha = tentativa
    linhas.append(linha)
    for i, texto in enumerate(linhas[:3]):
        desenho.text((540, 320 + i * 44), texto, font=fonte_funcao, fill=(139, 147, 163))
    desenho.text((540, 520), "Bot feito na Sora", font=fonte_rodape, fill=(r, g, b))
    saida = io.BytesIO()
    imagem.save(saida, format="PNG", optimize=True)
    return saida.getvalue()
