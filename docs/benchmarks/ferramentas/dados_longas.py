"""Dados fixos e gabarito das tarefas longas L01–L10 (tarefa 0.5, baseline).

Uso (de dentro de ``backend/``, que tem openpyxl):

    uv run python ../docs/benchmarks/ferramentas/dados_longas.py gerar     # reescreve dados/ e paginas/
    uv run python ../docs/benchmarks/ferramentas/dados_longas.py gabarito  # imprime o esperado

Os dados são escritos à mão aqui; o gabarito é CALCULADO a partir deles pelo mesmo código que o
executor (``rodar_longas.py``) usa para conferir. Nada de conta feita à mão no documento.
Nenhum título, nome de arquivo ou texto usa a palavra "Sora" (o título com "sora" é bloqueado no PC).
"""

from __future__ import annotations

import csv
import io
import json
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]  # docs/benchmarks
DADOS = RAIZ / "dados"
PAGINAS = RAIZ / "paginas"


def d2(valor: Decimal | float | int) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- L01: vendas por loja (CSV)
L01_VENDAS = [
    # id, data, loja (com sujeira de propósito), produto, quantidade, preco_unitario
    (1, "2026-11-02", "Centro", "Café 500 g", 12, "18.90"),
    (2, "2026-11-02", "Norte", "Café 500 g", 7, "18.90"),
    (3, "2026-11-02", " praia", "Filtro 103", 20, "6.50"),
    (4, "2026-11-03", "Serra", "Caneca", 5, "32.00"),
    (5, "2026-11-03", "centro ", "Filtro 103", 15, "6.50"),
    (6, "2026-11-03", "Norte", "Caneca", -2, "32.00"),
    (7, "2026-11-04", "Praia", "Café 1 kg", 9, "34.50"),
    (8, "2026-11-04", "SERRA", "Café 500 g", 11, "18.90"),
    (9, "2026-11-04", "Centro", "Café 1 kg", 6, "34.50"),
    (10, "2026-11-05", "Norte", "Filtro 103", 30, "6.50"),
    (11, "2026-11-05", "Praia", "Caneca", 4, "32.00"),
    (12, "2026-11-05", "Centro", "Caneca", -1, "32.00"),
    (13, "2026-11-06", "Serra", "Café 1 kg", 3, "34.50"),
    (14, "2026-11-06", "norte", "Café 1 kg", 8, "34.50"),
    (15, "2026-11-06", "Praia", "Café 500 g", 14, "18.90"),
    (16, "2026-11-07", "Centro", "Café 500 g", 10, "18.90"),
    (17, "2026-11-07", "Serra", "Filtro 103", 25, "6.50"),
    (18, "2026-11-07", "Praia", "Filtro 103", -5, "6.50"),
    (19, "2026-11-08", "Norte", "Café 500 g", 6, "18.90"),
    (20, "2026-11-08", "Centro", "Filtro 103", 18, "6.50"),
    (21, "2026-11-08", "Serra", "Caneca", 2, "32.00"),
    (22, "2026-11-09", " Praia ", "Café 1 kg", 5, "34.50"),
    (23, "2026-11-09", "Norte", "Caneca", 3, "32.00"),
    (24, "2026-11-09", "Centro", "Café 1 kg", 4, "34.50"),
]


def gabarito_l01() -> dict:
    totais: dict[str, Decimal] = {}
    descartadas = 0
    for _, _, loja, _, qtd, preco in L01_VENDAS:
        if qtd < 0:
            descartadas += 1
            continue
        nome = loja.strip().capitalize()
        totais[nome] = totais.get(nome, Decimal(0)) + qtd * Decimal(preco)
    lojas = sorted(({"loja": k, "total": d2(v)} for k, v in totais.items()), key=lambda x: -x["total"])
    media = d2(sum(x["total"] for x in lojas) / len(lojas))
    return {"lojas": lojas, "media": media, "devolucoes_descartadas": descartadas}


# ---------------------------------------------------------------- L02: memória em dois turnos
L02_PRAZO = date(2027, 3, 12)
L02_REFERENCIA = date(2027, 1, 15)


def gabarito_l02() -> dict:
    return {
        "cliente": "Padaria Aurora",
        "orcamento": "R$ 18.400",
        "prazo": "12/03/2027",
        "cor": "verde-musgo",
        "responsavel": "Bianca",
        "dias_ate_prazo": (L02_PRAZO - L02_REFERENCIA).days,
    }


# ---------------------------------------------------------------- L03: página de frete + pedidos
L03_REGIOES = {  # região: (base, por_kg)
    "Sudeste": ("12.00", "2.50"),
    "Sul": ("15.00", "3.00"),
    "Nordeste": ("18.00", "3.50"),
    "Norte": ("25.00", "4.20"),
}
L03_UF = {"SP": "Sudeste", "RJ": "Sudeste", "MG": "Sudeste", "PR": "Sul", "RS": "Sul",
          "BA": "Nordeste", "PE": "Nordeste", "AM": "Norte", "PA": "Norte"}
L03_PEDIDOS = [
    {"id": 301, "uf": "SP", "peso_kg": 2.0, "valor": 150.00},
    {"id": 302, "uf": "BA", "peso_kg": 4.5, "valor": 420.00},
    {"id": 303, "uf": "AM", "peso_kg": 1.2, "valor": 89.90},
    {"id": 304, "uf": "RS", "peso_kg": 3.0, "valor": 310.50},
    {"id": 305, "uf": "MG", "peso_kg": 7.5, "valor": 299.99},
    {"id": 306, "uf": "PE", "peso_kg": 0.8, "valor": 45.00},
    {"id": 307, "uf": "PA", "peso_kg": 5.0, "valor": 600.00},
    {"id": 308, "uf": "PR", "peso_kg": 2.2, "valor": 120.00},
]


def gabarito_l03() -> dict:
    linhas = []
    for p in sorted(L03_PEDIDOS, key=lambda p: p["id"]):
        regiao = L03_UF[p["uf"]]
        base, kg = (Decimal(x) for x in L03_REGIOES[regiao])
        frete = base + kg * Decimal(str(p["peso_kg"]))
        if Decimal(str(p["valor"])) > 300:
            frete = frete / 2
        linhas.append({"id": p["id"], "uf": p["uf"], "regiao": regiao, "frete": d2(frete)})
    maior = max(linhas, key=lambda x: x["frete"])
    return {"linhas": linhas, "total": d2(sum(x["frete"] for x in linhas)), "maior_id": maior["id"]}


# ---------------------------------------------------------------- L04: duas páginas + uma que não existe
L04_CATALOGO = [("A1", "Água mineral 1,5 L", "Bebidas"), ("A2", "Suco de uva 1 L", "Bebidas"),
                ("A3", "Arroz 5 kg", "Mercearia"), ("A4", "Feijão 1 kg", "Mercearia"),
                ("A5", "Detergente 500 ml", "Limpeza"), ("A6", "Desinfetante 2 L", "Limpeza")]
L04_PRECOS = {"A1": ("3.20", 40), "A2": ("11.90", 0), "A3": ("27.50", 12),
              "A4": ("8.40", 25), "A5": ("2.99", 60), "A6": ("14.75", 0)}


def gabarito_l04() -> dict:
    categorias: dict[str, Decimal] = {}
    sem = []
    for codigo, _, cat in L04_CATALOGO:
        preco, estoque = L04_PRECOS[codigo]
        if estoque <= 0:
            sem.append(codigo)
            continue
        categorias[cat] = categorias.get(cat, Decimal(0)) + Decimal(preco) * estoque
    categorias = {k: d2(v) for k, v in categorias.items()}
    return {"categorias": categorias, "itens_sem_estoque": sorted(sem),
            "maior_categoria": max(categorias, key=categorias.get)}


# ---------------------------------------------------------------- L05/L06/L07: servidor MCP de bancada
L05_ESTOQUE = [  # sku, nome, quantidade, minimo
    ("P-01", "Copo 300 ml", 40, 20), ("P-02", "Tampa 300 ml", 3, 10), ("P-03", "Canudo", 0, 5),
    ("P-04", "Guardanapo", 50, 30), ("P-05", "Mexedor", 7, 8), ("P-06", "Sacola", 15, 15),
]
L05_PRECOS = {"P-01": "0.35", "P-02": "4.50", "P-03": "12.90", "P-04": "2.10", "P-05": "7.25", "P-06": "0.80"}


def gabarito_l05() -> dict:
    itens = []
    for sku, _, qtd, minimo in L05_ESTOQUE:
        if qtd < minimo:
            falta = 2 * minimo - qtd
            preco = Decimal(L05_PRECOS[sku])
            itens.append({"sku": sku, "quantidade": falta, "preco_unitario": d2(preco), "subtotal": d2(falta * preco)})
    return {"itens": itens, "total": d2(sum(i["subtotal"] for i in itens))}


L06_FRETES = {"01310-100": "18.40", "20040-002": "22.10", "30130-010": "19.75",
              "69900-000": None, "80010-000": "24.30"}


def gabarito_l06() -> dict:
    ok = {k: d2(Decimal(v)) for k, v in L06_FRETES.items() if v is not None}
    return {"fretes": {k: (d2(Decimal(v)) if v else "INDISPONIVEL") for k, v in L06_FRETES.items()},
            "soma": d2(sum(ok.values())), "mais_caro": max(ok, key=ok.get)}


L07_ATENDIMENTOS = [  # dia, atendente, atendimentos
    ("segunda", "Ana", 14), ("segunda", "Rui", 9), ("terça", "Ana", 11), ("terça", "Rui", 12),
    ("quarta", "Ana", 18), ("quarta", "Rui", 7), ("quinta", "Ana", 10), ("quinta", "Rui", 10),
    ("sexta", "Ana", 16), ("sexta", "Rui", 13),
]


def gabarito_l07() -> dict:
    por_dia: dict[str, int] = {}
    for dia, _, n in L07_ATENDIMENTOS:
        por_dia[dia] = por_dia.get(dia, 0) + n
    media = (Decimal(sum(por_dia.values())) / len(por_dia)).quantize(Decimal("0.1"), ROUND_HALF_UP)
    return {"por_dia": por_dia, "maior_dia": max(por_dia, key=por_dia.get), "media": media}


# ---------------------------------------------------------------- L08/L09: pendências e agenda
L08_ABERTAS = ["Avisar clientes", "Contratar caminhão", "Ligar internet nova"]
L08_RESPOSTA = "domingo"
L09_ATIVOS = {  # título: (tipo esperado, início local AAAA-MM-DD HH:MM ou cron)
    "Treinamento módulo 1": "2027-02-08 09:00",
    "Treinamento módulo 2": "2027-03-01 09:00",
    "Treinamento módulo 3": "2027-02-22 09:00",
    "Revisão geral": "30 8 29 2 *",
}


# ---------------------------------------------------------------- L10: planilha com 3 abas, correção no 2º turno
L10_RECEITAS = [("jan", "Vendas balcão", 18200), ("jan", "Encomendas", 4300), ("fev", "Vendas balcão", 16900),
                ("fev", "Encomendas", 5100), ("mar", "Vendas balcão", 19400), ("mar", "Encomendas", 3800)]
L10_DESPESAS = [("jan", "Aluguel", 2400), ("jan", "Folha", 9800), ("jan", "Insumos", 6100),
                ("fev", "Aluguel", 4800), ("fev", "Folha", 9800), ("fev", "Insumos", 5900),
                ("mar", "Aluguel", 2400), ("mar", "Folha", 10100), ("mar", "Insumos", 6900)]
L10_METAS = [("jan", 4000), ("fev", 3000), ("mar", 4000)]


def gabarito_l10(corrigido: bool) -> dict:
    linhas = []
    for mes, meta in L10_METAS:
        rec = sum(v for m, _, v in L10_RECEITAS if m == mes)
        desp = sum((v / 2 if (corrigido and m == "fev" and d == "Aluguel") else v)
                   for m, d, v in L10_DESPESAS if m == mes)
        saldo = rec - desp
        linhas.append({"mes": mes, "receitas": d2(rec), "despesas": d2(desp), "saldo": d2(saldo),
                       "meta": d2(meta), "atingiu": "sim" if saldo >= meta else "nao"})
    return {"linhas": linhas, "pior_mes": min(linhas, key=lambda x: x["saldo"])["mes"]}


GABARITOS = {
    "L01": gabarito_l01, "L02": gabarito_l02, "L03": gabarito_l03, "L04": gabarito_l04,
    "L05": gabarito_l05, "L06": gabarito_l06, "L07": gabarito_l07,
    "L08": lambda: {"abertas": L08_ABERTAS, "dia": L08_RESPOSTA},
    "L09": lambda: {"ativos": L09_ATIVOS},
    "L10": lambda: {"v1": gabarito_l10(False), "v2": gabarito_l10(True)},
}


# ---------------------------------------------------------------- geração dos arquivos
def _csv(linhas: list[list], cabecalho: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cabecalho)
    w.writerows(linhas)
    return buf.getvalue()


def gerar() -> None:
    DADOS.mkdir(exist_ok=True)
    PAGINAS.mkdir(exist_ok=True)
    (DADOS / "vendas_L01.csv").write_text(
        _csv([list(r) for r in L01_VENDAS], ["id", "data", "loja", "produto", "quantidade", "preco_unitario"]),
        encoding="utf-8")
    (DADOS / "pedidos_L03.json").write_text(json.dumps(L03_PEDIDOS, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    (DADOS / "relatorio_L07.csv").write_text(
        _csv([list(r) for r in L07_ATENDIMENTOS], ["dia", "atendente", "atendimentos"]), encoding="utf-8")

    from openpyxl import Workbook

    wb = Workbook()
    aba = wb.active
    aba.title = "Receitas"
    aba.append(["mes", "descricao", "valor"])
    for r in L10_RECEITAS:
        aba.append(list(r))
    aba = wb.create_sheet("Despesas")
    aba.append(["mes", "descricao", "valor"])
    for r in L10_DESPESAS:
        aba.append(list(r))
    aba = wb.create_sheet("Metas")
    aba.append(["mes", "meta_saldo"])
    for r in L10_METAS:
        aba.append(list(r))
    # data fixa nas propriedades (o zip ainda grava a hora: gere uma vez e commite o arquivo)
    from datetime import datetime

    wb.properties.created = wb.properties.modified = datetime(2026, 11, 25)
    wb.save(DADOS / "orcamento_L10.xlsx")

    regioes = "\n".join(f"| {r} | {b} | {k} |" for r, (b, k) in L03_REGIOES.items())
    ufs = "\n".join(f"| {uf} | {r} |" for uf, r in L03_UF.items())
    (PAGINAS / "L03_frete.md").write_text(
        "# Tabela de frete da bancada L03\n\nValores em reais. Frete = base + por_kg × peso em kg.\n"
        "Pedidos com valor acima de R$ 300,00 têm 50% de desconto no frete.\n\n"
        f"## Região\n\n| Região | Base | Por kg |\n|---|---|---|\n{regioes}\n\n"
        f"## UF para região\n\n| UF | Região |\n|---|---|\n{ufs}\n", encoding="utf-8")
    cat = "\n".join(f"| {c} | {n} | {g} |" for c, n, g in L04_CATALOGO)
    (PAGINAS / "L04_catalogo.md").write_text(
        f"# Catálogo da bancada L04\n\n| Código | Produto | Categoria |\n|---|---|---|\n{cat}\n", encoding="utf-8")
    pre = "\n".join(f"| {c} | {p} | {e} |" for c, (p, e) in L04_PRECOS.items())
    (PAGINAS / "L04_precos.md").write_text(
        f"# Preços e estoque da bancada L04\n\nPreço em reais por unidade.\n\n"
        f"| Código | Preço | Estoque |\n|---|---|---|\n{pre}\n", encoding="utf-8")


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else "gabarito"
    if acao == "gerar":
        gerar()
        print("dados e páginas gerados em", RAIZ)
    else:
        for k, f in GABARITOS.items():
            print(k, _json(f()))
