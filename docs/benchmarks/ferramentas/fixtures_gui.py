"""Fixtures de tela G01–G10 e reproduções R1/R3: prepara os arquivos e confere a prova FORA do bot.

Não é código do produto. Roda de dentro de ``backend/`` (tem openpyxl e python-docx):

    uv run python ../docs/benchmarks/ferramentas/fixtures_gui.py preparar [--pasta C:\\bancada-g]
    uv run python ../docs/benchmarks/ferramentas/fixtures_gui.py conferir G02|G05|G07|G08|G09|G10 [--pasta ...]
    uv run python ../docs/benchmarks/ferramentas/fixtures_gui.py formulario     # servidor da G09/G10 em 127.0.0.1:8766

O que é lido pela tela (texto do Bloco de Notas, visor da Calculadora, janela em primeiro plano,
Excel aberto) é conferido por ``conferir_g.ps1`` (UI Automation / COM, só leitura).
Nenhum nome de arquivo ou título usa a palavra "Sora" (o título com "sora" é bloqueado no PC).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

PASTA_PADRAO = Path(r"C:\bancada-g")
PORTA_FORM = 8766

G02_ANTES = "lista de compras da bancada\nproduto: café\nquantidade: 10\nunidade: pacote\nfim da lista\n"
G02_DEPOIS = G02_ANTES.replace("quantidade: 10", "quantidade: 25")
G04_A = "Arquivo A da bancada G04.\n"
G10_INTRUSO = "Janela intrusa da bancada G10. Nada deve ser digitado aqui.\n"

G05_LOJAS = [  # loja, vendas, devolucoes, saldo_final
    ("Centro", 51230.10, 1210.40, 50019.70), ("Bairro Alto", 49102.66, 785.40, 48317.26),
    ("Portão", 38770.00, 990.15, 37779.85), ("Água Verde", 45010.90, 312.00, 44698.90),
    ("Batel", 60230.45, 2003.10, 58227.35), ("Boqueirão", 29870.30, 120.00, 29750.30),
]
G05_ESPERADO = "48317.26"

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
         "Outubro", "Novembro", "Dezembro"]
G07_MUDANCAS = {("Filial 07", "Março"): 1500, ("Filial 13", "Agosto"): 2750, ("Filial 19", "Dezembro"): 980}

G08_TITULO = "Relatório de bancada"
G08_PARAGRAFOS = [
    "Este documento serve de fixture para a bancada de tela G08.",
    "O segundo parágrafo vem antes da tabela que o bot deve inserir.",
    "O terceiro parágrafo tem a palavra urgente, que deve ficar sublinhada.",
]
G08_TABELA = [["Item", "Valor"], ["Café", "12"]]

G09_ESPERADO = {"nome": "Marina Duarte", "email": "marina@exemplo.com.br", "cidade": "Curitiba",
                "quantidade": "7", "aceite": "sim"}
G10_ESPERADO = {"nome": "Otávio Lins", "email": "otavio@exemplo.com.br", "cidade": "Londrina",
                "quantidade": "3", "aceite": "sim", "codigo": "K7-42"}


# ------------------------------------------------------------------------------- pedidos exatos (copiados pelo nova-g)
PEDIDOS_G = {
    "G01": ("No meu computador, abra o Bloco de Notas em um documento novo e escreva exatamente estas três linhas, "
            "uma embaixo da outra: 'Linha um da bancada', 'Linha dois: 2 + 2 = 4' e 'Linha três termina aqui.' "
            "(sem as aspas). Não salve e deixe a janela aberta."),
    "G02": ("No meu computador, no Bloco de Notas que está aberto com o arquivo G02_lista.txt, troque a linha "
            "'quantidade: 10' por 'quantidade: 25' sem mudar mais nada e salve com Ctrl+S. Depois feche a aba do arquivo "
            "com Ctrl+W, reabra o mesmo arquivo com Ctrl+O digitando C:\\bancada-g\\G02_lista.txt e Enter, e confira "
            "que a mudança ficou salva. Deixe o arquivo aberto."),
    "G03": ("No meu computador, na Calculadora que está aberta, calcule (1234 + 5678) × 3 − 99 e me diga o resultado "
            "que aparece no visor."),
    "G04": ("No meu computador, traga a janela do Paint para a frente; depois volte para o Bloco de Notas com o arquivo "
            "G04_a.txt e deixe ele em primeiro plano. Não digite nada em nenhum dos dois."),
    "G05": ("No meu computador, no Excel aberto com G05_valores.xlsx, leia e me diga o valor exato do 'Saldo final' da "
            "loja Bairro Alto. Não altere a planilha."),
    "G06": ("No meu computador, no Bloco de Notas aberto (documento novo e vazio), faça estas 15 ações em ordem: "
            "1) escreva 'alfa beta gama'; 2) tecle Enter; 3) escreva 'delta'; 4) tecle Enter; 5) escreva 'epsilon zeta'; "
            "6) tecle Ctrl+Home; 7) escreva 'Lista: ' (com o espaço no fim); 8) tecle End; 9) escreva ' (1)'; "
            "10) tecle seta para baixo e depois End; 11) escreva ' (2)'; 12) tecle seta para baixo e depois End; "
            "13) apague ' zeta' com 5 Backspace; 14) escreva ' (3)'; 15) tecle Ctrl+End, depois Enter, e escreva 'fim'. "
            "Escreva sem as aspas e não salve. No fim, confira o texto e me diga como ficou."),
    "G07": ("No meu computador, no Excel aberto com G07_grade.xlsx, mude só estas três células: Março da 'Filial 07' "
            "para 1500, Agosto da 'Filial 13' para 2750 e Dezembro da 'Filial 19' para 980. Não mude mais nada e salve "
            "com Ctrl+S."),
    "G08": ("No meu computador, no Word aberto com G08_documento.docx: 1) deixe a primeira linha, 'Relatório de "
            "bancada', em negrito; 2) insira uma tabela de 2 linhas e 2 colunas logo depois do segundo parágrafo, com "
            "'Item' e 'Valor' na primeira linha e 'Café' e '12' na segunda; 3) sublinhe só a palavra 'urgente' no "
            "terceiro parágrafo; 4) salve com Ctrl+S, sem mudar o nome nem o formato do arquivo."),
    "G09": ("No meu computador, no navegador aberto na página 'Cadastro de bancada G09', preencha: Nome 'Marina "
            "Duarte', E-mail 'marina@exemplo.com.br', Cidade 'Curitiba', Quantidade 7, marque 'Aceito os termos' e "
            "clique em Enviar. Depois me diga o número de protocolo que aparecer na tela."),
    "G10": ("No meu computador, no navegador aberto na página 'Cadastro de bancada G10', espere o formulário carregar "
            "e preencha: Nome 'Otávio Lins', E-mail 'otavio@exemplo.com.br', Cidade 'Londrina', Quantidade 3, marque "
            "'Aceito os termos' e clique em Enviar. Depois de clicar, vai aparecer o campo 'Código de confirmação': "
            "preencha 'K7-42' e clique em Enviar de novo. Se outra janela aparecer na frente, não mexa nela: volte para "
            "o navegador. No fim, me diga o protocolo."),
    # Reproduções das falhas reais (texto original dos logs de 21 e 22/11)
    "R1": "acesse meu computador e monte uma tabela simples no meu Excel com cores e títulos sublinhados",
    "R3": ("No meu computador, abra o Bloco de Notas e escreva ‘Teste da Sora’. Deixe a janela aberta para eu "
           "conferir. Use um documento novo e preserve qualquer documento já aberto."),
}
G01_ESPERADO = "Linha um da bancada\nLinha dois: 2 + 2 = 4\nLinha três termina aqui."
G03_ESPERADO = "20637"
G06_ESPERADO = "Lista: alfa beta gama (1)\ndelta (2)\nepsilon (3)\nfim"
R3_ESPERADO = "Teste da Sora"


def _sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _g07_valor(linha: int, coluna: int) -> int:
    return 100 + (linha * 37 + coluna * 53) % 900


# ------------------------------------------------------------------------------- preparar
def preparar(pasta: Path) -> None:
    from docx import Document
    from openpyxl import Workbook

    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "originais").mkdir(exist_ok=True)
    (pasta / "G02_lista.txt").write_text(G02_ANTES, encoding="utf-8")
    (pasta / "G04_a.txt").write_text(G04_A, encoding="utf-8")
    (pasta / "G10_intruso.txt").write_text(G10_INTRUSO, encoding="utf-8")

    wb = Workbook()
    aba = wb.active
    aba.title = "Painel"
    aba.append(["Painel de lojas da bancada G05"])
    aba.append([])
    aba.append(["Loja", "Vendas", "Devoluções", "Saldo final"])
    for linha in G05_LOJAS:
        aba.append(list(linha))
    for c in "BCD":
        for r in range(4, 4 + len(G05_LOJAS)):
            aba[f"{c}{r}"].number_format = "#,##0.00"
    wb.save(pasta / "G05_valores.xlsx")

    wb = Workbook()
    aba = wb.active
    aba.title = "Grade"
    aba.append(["Filial", *MESES])
    for i in range(1, 21):
        aba.append([f"Filial {i:02d}", *[_g07_valor(i, j) for j in range(1, 13)]])
    wb.save(pasta / "G07_grade.xlsx")

    doc = Document()
    doc.add_paragraph(G08_TITULO)  # parágrafo normal: o negrito tem de ser aplicado pelo bot
    for p in G08_PARAGRAFOS:
        doc.add_paragraph(p)
    doc.save(pasta / "G08_documento.docx")

    for nome in ("G02_lista.txt", "G04_a.txt", "G05_valores.xlsx", "G07_grade.xlsx", "G08_documento.docx", "G10_intruso.txt"):
        (pasta / "originais" / nome).write_bytes((pasta / nome).read_bytes())
    for nome in ("G09_envios.json", "G10_envios.json"):
        (pasta / nome).unlink(missing_ok=True)
    manifesto = {nome: _sha(pasta / nome) for nome in sorted(p.name for p in pasta.iterdir() if p.is_file())}
    (pasta / "manifesto.json").write_text(json.dumps(manifesto, indent=1), encoding="utf-8")
    print(f"fixtures prontas em {pasta}:", ", ".join(manifesto))


# ------------------------------------------------------------------------------- conferir
def conferir(caso: str, pasta: Path) -> dict:
    criterios: list[tuple[str, bool]] = []
    extra: dict = {}
    if caso == "G02":
        texto = (pasta / "G02_lista.txt").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        criterios.append(("arquivo salvo com 'quantidade: 25'", "quantidade: 25" in texto))
        criterios.append(("resto do arquivo igual (só a linha pedida mudou)", texto.rstrip("\n") == G02_DEPOIS.rstrip("\n")))
    elif caso == "G05":
        from openpyxl import load_workbook

        aba = load_workbook(pasta / "G05_valores.xlsx", data_only=True)["Painel"]
        valor = next(r[3].value for r in aba.iter_rows(min_row=4) if r[0].value == "Bairro Alto")
        criterios.append(("fixture intacta (valor de referência)", f"{valor:.2f}" == G05_ESPERADO))
        criterios.append(("arquivo não foi alterado pelo bot", _sha(pasta / "G05_valores.xlsx") == _sha(pasta / "originais" / "G05_valores.xlsx")))
        extra["valor_certo"] = "48.317,26"
    elif caso == "G07":
        from openpyxl import load_workbook

        aba = load_workbook(pasta / "G07_grade.xlsx", data_only=True)["Grade"]
        cab = [c.value for c in aba[1]]
        diferencas, mudancas_ok = [], 0
        for r in range(2, 22):
            filial = aba.cell(r, 1).value
            for j, mes in enumerate(MESES, start=2):
                obtido = aba.cell(r, j).value
                esperado = G07_MUDANCAS.get((filial, mes), _g07_valor(r - 1, j - 1))
                if obtido != esperado:
                    diferencas.append(f"{filial}/{mes}: {obtido} (esperado {esperado})")
                elif (filial, mes) in G07_MUDANCAS:
                    mudancas_ok += 1
        criterios.append(("cabeçalho intacto", cab == ["Filial", *MESES]))
        criterios.append((f"3 mudanças pedidas ({mudancas_ok}/3)", mudancas_ok == 3))
        criterios.append(("nenhuma outra célula mudou", not [d for d in diferencas if not any(f"{f}/{m}" in d for f, m in G07_MUDANCAS)]))
        extra["diferencas"] = diferencas[:20]
    elif caso == "G08":
        from docx import Document

        doc = Document(pasta / "G08_documento.docx")
        corpo = doc.element.body
        ordem = [el.tag.rsplit("}", 1)[-1] for el in corpo.iterchildren() if el.tag.rsplit("}", 1)[-1] in ("p", "tbl")]
        paragrafos = [p for p in doc.paragraphs if p.text.strip()]
        titulo = next((p for p in paragrafos if p.text.strip() == G08_TITULO), None)
        criterios.append(("título em negrito", bool(titulo) and all(r.bold for r in titulo.runs if r.text.strip())))
        tabelas = doc.tables
        celulas = [[c.text.strip() for c in linha.cells] for linha in tabelas[0].rows] if tabelas else []
        criterios.append(("tabela 2×2 com Item/Valor e Café/12", celulas == G08_TABELA))
        # a tabela fica depois do 2º parágrafo de texto e antes do 3º
        textos = []
        for el in corpo.iterchildren():
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "tbl":
                textos.append("<TABELA>")
            elif tag == "p":
                t = "".join(x.text or "" for x in el.iter() if x.tag.endswith("}t")).strip()
                if t:
                    textos.append(t)
        pos = textos.index("<TABELA>") if "<TABELA>" in textos else -1
        criterios.append(("tabela entre o 2º e o 3º parágrafo", pos > 0 and textos[pos - 1] == G08_PARAGRAFOS[1] and pos + 1 < len(textos) and textos[pos + 1] == G08_PARAGRAFOS[2]))
        terceiro = next((p for p in doc.paragraphs if "urgente" in p.text), None)
        sub = [r for r in (terceiro.runs if terceiro else []) if "urgente" in r.text]
        criterios.append(("'urgente' sublinhada (só ela)", bool(sub) and all(r.underline for r in sub) and all(r.text.strip() == "urgente" for r in sub)
                          and not any(r.underline for r in terceiro.runs if "urgente" not in r.text)))
        criterios.append(("textos originais preservados", all(any(p.text.strip() == t for p in doc.paragraphs) for t in G08_PARAGRAFOS)))
        extra["ordem"] = textos
    elif caso in ("G09", "G10"):
        arq = pasta / f"{caso}_envios.json"
        envios = json.loads(arq.read_text("utf-8")) if arq.exists() else []
        esperado = G09_ESPERADO if caso == "G09" else G10_ESPERADO
        criterios.append(("exatamente 1 envio", len(envios) == 1))
        if envios:
            ultimo = envios[-1]
            campos = {k: str(ultimo.get(k, "")).strip() for k in esperado}
            erradas = {k: campos[k] for k in esperado if campos[k] != esperado[k]}
            criterios.append(("campos exatos", not erradas))
            extra.update({"protocolo": ultimo.get("protocolo"), "campos_errados": erradas})
        if caso == "G10":
            texto = (pasta / "G10_intruso.txt").read_text(encoding="utf-8")
            criterios.append(("janela intrusa intocada (arquivo)", texto == G10_INTRUSO))
    else:
        raise SystemExit(f"{caso}: conferido pela tela com conferir_g.ps1 (veja fixtures-gui.md)")
    ok = sum(1 for _, x in criterios if x)
    resultado = "ok" if ok == len(criterios) else ("parcial" if ok else "falhou")
    saida = {"caso": caso, "resultado_arquivo": resultado, "criterios": [{"criterio": n, "ok": x} for n, x in criterios], **extra}
    print(json.dumps(saida, ensure_ascii=False, indent=1))
    return saida


# ------------------------------------------------------------------------------- formulário G09/G10
PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{titulo}</title>
<style>body{{font:16px Segoe UI,sans-serif;margin:40px;max-width:520px}}label{{display:block;margin:14px 0 4px}}
input,select{{font-size:16px;padding:6px;width:100%}}button{{margin-top:18px;font-size:16px;padding:8px 18px}}
#carregando{{color:#555}}</style></head><body><h1>{titulo}</h1>{corpo}</body></html>"""

CAMPOS = """<form method="post" action="/enviar/{caso}">
<label for="nome">Nome</label><input id="nome" name="nome" autocomplete="off">
<label for="email">E-mail</label><input id="email" name="email" autocomplete="off">
<label for="cidade">Cidade</label><select id="cidade" name="cidade"><option value="">Escolha…</option>
<option>Curitiba</option><option>Londrina</option><option>Maringá</option><option>Cascavel</option></select>
<label for="quantidade">Quantidade</label><input id="quantidade" name="quantidade" type="number" min="1" max="99">
<label><input type="checkbox" name="aceite" value="sim" style="width:auto"> Aceito os termos</label>
{extra}<button type="submit">Enviar</button></form>"""

G10_JS = """<p id="carregando">Carregando o formulário…</p><div id="area" hidden>{campos}</div>
<script>setTimeout(()=>{{document.getElementById('carregando').hidden=true;document.getElementById('area').hidden=false;}},5000);
const f=()=>document.querySelector('form');
setTimeout(()=>{{const b=f().querySelector('button');b.addEventListener('click',(e)=>{{const c=document.getElementById('codigo');
if(c.hidden){{e.preventDefault();b.textContent='Aguarde…';setTimeout(()=>{{c.hidden=false;document.getElementById('rot').hidden=false;b.textContent='Enviar';}},3000);}}}});}},5100);</script>"""


def servidor_formulario(pasta: Path) -> None:
    class Manipulador(BaseHTTPRequestHandler):
        def _html(self, html: str, status: int = 200) -> None:
            dados = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/g10"):
                extra = ('<label id="rot" for="codigo" hidden>Código de confirmação</label>'
                         '<input id="codigo" name="codigo" hidden autocomplete="off">')
                campos = CAMPOS.format(caso="G10", extra=extra)
                self._html(PAGINA.format(titulo="Cadastro de bancada G10", corpo=G10_JS.format(campos=campos)))
            else:
                self._html(PAGINA.format(titulo="Cadastro de bancada G09", corpo=CAMPOS.format(caso="G09", extra="")))

        def do_POST(self) -> None:  # noqa: N802
            caso = "G10" if self.path.endswith("G10") else "G09"
            tamanho = int(self.headers.get("Content-Length") or 0)
            campos = {k: v[0] for k, v in parse_qs(self.rfile.read(tamanho).decode("utf-8")).items()}
            arq = pasta / f"{caso}_envios.json"
            envios = json.loads(arq.read_text("utf-8")) if arq.exists() else []
            protocolo = f"{caso}-{len(envios) + 1:03d}-{int(time.time()) % 10000:04d}"
            envios.append({**campos, "protocolo": protocolo, "t": time.time()})
            arq.write_text(json.dumps(envios, ensure_ascii=False, indent=1), "utf-8")
            self._html(PAGINA.format(titulo=f"Cadastro de bancada {caso}",
                                     corpo=f"<p>Recebido. Protocolo: <strong id=\"protocolo\">{protocolo}</strong></p>"))

        def log_message(self, *args) -> None:
            return None

    print(f"formulário em http://127.0.0.1:{PORTA_FORM}/ (G09) e /g10 (G10); envios em {pasta}")
    ThreadingHTTPServer(("127.0.0.1", PORTA_FORM), Manipulador).serve_forever()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["preparar", "conferir", "formulario"])
    ap.add_argument("caso", nargs="?")
    ap.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    a = ap.parse_args()
    if a.acao == "preparar":
        preparar(a.pasta)
    elif a.acao == "conferir":
        conferir(a.caso.upper(), a.pasta)
    else:
        servidor_formulario(a.pasta)
