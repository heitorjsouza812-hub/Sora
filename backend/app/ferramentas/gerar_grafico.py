"""Ferramenta ``gerar_grafico``: desenha um gráfico a partir de um JSON simples e devolve um
PNG que vira anexo.

Adaptado do Rakazo (github.com/elie222/rakazo, Apache-2.0): ``adapters/src/plot-tool.ts`` e
``core/src/plot.ts`` (gráfico por especificação, com limites de séries e pontos). O Rakazo
desenha em outra biblioteca; aqui é o matplotlib (backend Agg, sem tela), numa thread para
não travar o worker.
"""

from __future__ import annotations

import asyncio
import io
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.ferramentas.base import ErroFerramenta

MAX_SERIES = 12
MAX_PONTOS = 5_000
CORES_SORA = ["#56A8FF", "#AC80FF", "#46E8A8", "#FFB45A", "#FF6B8B", "#7EF2C4", "#E2ECFF"]
"""Cores dos agentes de exemplo + destaques do app (``CLAUDE.md`` §3.1 e §4.1)."""

DESCRICAO = (
    "Desenha um gráfico (barra, linha, área, dispersão, histograma ou pizza) com os dados que "
    "você passar e anexa a imagem. Use só dados reais; nunca invente números."
)


class Serie(BaseModel):
    nome: str = Field(default="", max_length=60)
    x: list[str | float] = Field(default_factory=list)
    y: list[float] = Field(default_factory=list)


class GerarGrafico(BaseModel):
    """Desenha um gráfico e anexa a imagem PNG."""

    tipo: Literal["barra", "linha", "area", "dispersao", "histograma", "pizza"]
    titulo: str = Field(default="", max_length=120)
    rotulo_x: str = Field(default="", max_length=60)
    rotulo_y: str = Field(default="", max_length=60)
    series: list[Serie] = Field(min_length=1, max_length=MAX_SERIES)
    escala_log: bool = False

    @model_validator(mode="after")
    def _dados_coerentes(self) -> GerarGrafico:
        total = 0
        for serie in self.series:
            if self.tipo == "histograma":
                if not serie.y:
                    raise ValueError("histograma precisa de valores em 'y'")
            else:
                if len(serie.x) != len(serie.y) or not serie.y:
                    raise ValueError("cada série precisa de 'x' e 'y' do mesmo tamanho")
            total += len(serie.y)
        if total > MAX_PONTOS:
            raise ValueError(f"no máximo {MAX_PONTOS} pontos")
        if self.tipo == "pizza" and len(self.series) != 1:
            raise ValueError("pizza usa uma série só")
        if self.tipo == "dispersao" and any(isinstance(v, str) for s in self.series for v in s.x):
            raise ValueError("dispersão precisa de 'x' numérico")
        return self


def _desenhar(args: GerarGrafico) -> bytes:
    # ``Figure`` direto (sem pyplot): não usa estado global, então é seguro em threads.
    from matplotlib.figure import Figure

    figura = Figure(figsize=(8, 4.5), dpi=144)
    eixo = figura.subplots()
    figura.patch.set_facecolor("#0F1115")
    eixo.set_facecolor("#0F1115")
    for lado in eixo.spines.values():
        lado.set_color("#2A2D35")
    eixo.tick_params(colors="#8B93A3")
    eixo.title.set_color("#F2F5FB")
    eixo.xaxis.label.set_color("#8B93A3")
    eixo.yaxis.label.set_color("#8B93A3")
    varias = len(args.series) > 1
    if args.tipo == "pizza":
        serie = args.series[0]
        eixo.pie(
            serie.y,
            labels=[str(v) for v in serie.x],
            colors=CORES_SORA,
            textprops={"color": "#F2F5FB"},
            autopct="%1.0f%%",
        )
        eixo.axis("equal")
    elif args.tipo == "barra":
        largura = 0.8 / len(args.series)
        categorias = [str(v) for v in args.series[0].x]
        for i, serie in enumerate(args.series):
            posicoes = [p + i * largura - 0.4 + largura / 2 for p in range(len(serie.y))]
            eixo.bar(
                posicoes,
                serie.y,
                width=largura,
                label=serie.nome or None,
                color=CORES_SORA[i % len(CORES_SORA)],
            )
        eixo.set_xticks(range(len(categorias)), categorias)
    elif args.tipo == "histograma":
        for i, serie in enumerate(args.series):
            eixo.hist(
                serie.y,
                bins="auto",
                alpha=0.75 if varias else 1,
                label=serie.nome or None,
                color=CORES_SORA[i % len(CORES_SORA)],
            )
    else:
        for i, serie in enumerate(args.series):
            cor = CORES_SORA[i % len(CORES_SORA)]
            x = [str(v) for v in serie.x] if any(isinstance(v, str) for v in serie.x) else serie.x
            if args.tipo == "dispersao":
                eixo.scatter(x, serie.y, label=serie.nome or None, color=cor, s=18)
            else:
                eixo.plot(x, serie.y, label=serie.nome or None, color=cor, linewidth=2)
                if args.tipo == "area":
                    eixo.fill_between(x, serie.y, alpha=0.25, color=cor)
    if args.escala_log and args.tipo != "pizza":
        eixo.set_yscale("log")
    if args.titulo:
        eixo.set_title(args.titulo)
    if args.rotulo_x:
        eixo.set_xlabel(args.rotulo_x)
    if args.rotulo_y:
        eixo.set_ylabel(args.rotulo_y)
    if varias and any(s.nome for s in args.series):
        legenda = eixo.legend(frameon=False)
        for texto in legenda.get_texts():
            texto.set_color("#F2F5FB")
    figura.tight_layout()
    saida = io.BytesIO()
    figura.savefig(saida, format="png", facecolor=figura.get_facecolor())
    return saida.getvalue()


async def gerar_grafico(args: GerarGrafico) -> bytes:
    """PNG do gráfico. Erro de desenho volta para o modelo como erro de ferramenta."""
    try:
        return await asyncio.to_thread(_desenhar, args)
    except (ValueError, TypeError) as erro:
        raise ErroFerramenta(f"Não consegui desenhar o gráfico: {erro}") from erro
