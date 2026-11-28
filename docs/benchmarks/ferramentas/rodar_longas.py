"""Executor das tarefas longas L01–L10 (tarefa 0.5, baseline). Fala com o backend real só por
HTTP + SSE (como o app) e confere a prova FORA do bot: arquivo baixado da API, linhas no Postgres
(memórias, pendências, rotinas, habilidades, aprovações, chamadas de modelo) e o registro do
servidor MCP de bancada. Não é código do produto.

Rodar de dentro de ``backend/`` (usa o ``.env`` de lá; a chave da Groq é lida e NUNCA impressa):

    uv run python ../docs/benchmarks/ferramentas/rodar_longas.py preparar      # conta de QA + modelo fixo + conector
    uv run python ../docs/benchmarks/ferramentas/rodar_longas.py modelos       # lista provedores e modelos da conta
    uv run python ../docs/benchmarks/ferramentas/rodar_longas.py rodar L01 L02 --vezes 3 --log-worker CAMINHO
    uv run python ../docs/benchmarks/ferramentas/rodar_longas.py resumo        # linhas para o baseline.md
    uv run python ../docs/benchmarks/ferramentas/rodar_longas.py pedidos       # imprime os pedidos exatos

Pré-requisitos: Docker (Postgres + Redis), ``alembic upgrade head`` no banco LOCAL, API em 8000 e
``SORA_RASTRO=1 uv run python -m workers`` com a saída gravada em arquivo (``--log-worker``).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import dados_longas as D  # noqa: E402

RAIZ = AQUI.parent  # docs/benchmarks
BACKEND = RAIZ.parent.parent / "backend"
EXECUCOES = RAIZ / "execucoes"
ESTADO = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "sora-baseline" / "estado.json"
API = os.environ.get("SORA_QA_API", "http://localhost:8000")
# Modelo fixo do baseline e do Gate (§8). Trocado em 2026-11-26 por decisão do Heitor (baseline.md §2):
# o anterior, groq/qwen/qwen3.8-27b, ficou como histórico (a chave de QA recusa com 413 todo pedido
# acima de 7 000 tokens de entrada).
MODELO_ANTERIOR = "groq/qwen/qwen3.8-27b"
MODELO_FIXO = os.environ.get("BASELINE_MODELO", "gemini/gemini-3.5-flash-lite")
TIPO_PROVEDOR = {"gemini": "google", "groq": "groq"}[MODELO_FIXO.split("/", 1)[0]]
MODELO_ID_PROVEDOR = MODELO_FIXO.split("/", 1)[1]
PORTA_MCP = 8765
SENHA_QA = "baseline-qa-senha-0-5"
# Páginas fixture: servidas pelo raw do GitHub FIXADO num commit (o ler_pagina recusa 127.0.0.1).
PAGINAS_SHA = os.environ.get("BASELINE_PAGINAS_SHA", "54cd737395d79ea4f08b3667fe4e008eaaec8c60")
URL_PAGINAS = f"https://raw.githubusercontent.com/heitorjsouza812-hub/Sora/{PAGINAS_SHA}/docs/benchmarks/paginas"
PRAZO_TURNO_S = 900  # o job tem 360 s; 900 s cobre esperas de 429 e retomadas por cartão
FERRAMENTAS_BOT = ["ler_anexo", "ler_pagina", "escrever_arquivo"]
PAPEL_BOT = (
    "Você é um bot de bancada de testes. Faça exatamente o que o usuário pedir, na ordem pedida, "
    "usando as ferramentas. Nunca invente um resultado: se uma ferramenta falhar, diga qual falhou "
    "e o motivo."
)


# ------------------------------------------------------------------------------- fixtures
@dataclass
class Turno:
    texto: str
    resposta_pergunta: str | None = None  # valor/rotulo que o "usuário" escolhe
    decisao_cartao: str = "permitir_uma_vez"  # ou "negar"


@dataclass
class Fixture:
    id: str
    titulo: str
    anexos: list[str]
    turnos: list[Turno]
    usa_mcp: bool = False
    cartao_esperado: str = ""  # texto livre para o relatório


def _fixtures() -> dict[str, Fixture]:
    p = URL_PAGINAS
    return {
        "L01": Fixture("L01", "Vendas por loja: CSV → JSON + memória", ["vendas_L01.csv"], [Turno(
            "Anexei vendas_L01.csv. Faça nesta ordem: 1) leia o arquivo; 2) normalize o nome da loja "
            "(sem espaços nas pontas, só a primeira letra maiúscula); 3) descarte as linhas com quantidade "
            "negativa (são devoluções) e conte quantas descartou; 4) calcule o faturamento de cada linha "
            "(quantidade × preço unitário); 5) some o faturamento por loja; 6) arredonde cada total para 2 "
            "casas; 7) ordene as lojas do maior para o menor total; 8) calcule a média dos totais das lojas, "
            "com 2 casas; 9) salve o arquivo resumo_L01.json exatamente neste formato: "
            '{"lojas":[{"loja":"Nome","total":0.00}],"media":0.00,"devolucoes_descartadas":0}; '
            '10) guarde na memória o fato "Loja campeã de vendas (L01): <nome da loja>"; '
            "11) responda só com o nome da loja campeã e o total dela.")]),
        "L02": Fixture("L02", "Memória em dois turnos com troca aprovada", [], [
            Turno("Guarde na memória, um fato por vez, estes 5 fatos do projeto Ipê: "
                  "(a) O cliente do projeto Ipê é a Padaria Aurora. (b) O orçamento do projeto Ipê é R$ 18.400. "
                  "(c) O prazo do projeto Ipê é 12/03/2027. (d) A cor principal do projeto Ipê é verde-musgo. "
                  "(e) O responsável do projeto Ipê é o Caio. Depois me diga quantos fatos guardou."),
            Turno("Mudou uma coisa: o responsável do projeto Ipê agora é a Bianca. Faça nesta ordem: "
                  "1) busque na memória os fatos do projeto Ipê; 2) apague a memória antiga do responsável "
                  "(isso vai pedir minha aprovação); 3) guarde o fato novo do responsável; 4) busque de novo "
                  "para conferir; 5) calcule quantos dias faltam de 15/01/2027 até o prazo do projeto; "
                  "6) salve ipe_L02.md com uma linha por item no formato 'campo: valor', com os campos "
                  "cliente, orcamento, prazo, cor, responsavel e dias_ate_prazo; 7) responda só com o nome "
                  "do responsável atual."),
        ], cartao_esperado="esquecer_memoria (cartão fixo) → Permitir uma vez"),
        "L03": Fixture("L03", "Página de frete + pedidos anexos → CSV", ["pedidos_L03.json"], [Turno(
            f"Leia a tabela de frete em {p}/L03_frete.md e os pedidos do anexo pedidos_L03.json. Para cada "
            "pedido: 1) ache a região da UF pela tabela; 2) calcule frete = base + por_kg × peso; 3) se o "
            "valor do pedido passar de 300, aplique 50% de desconto no frete; 4) arredonde para 2 casas. "
            "Depois: 5) some o frete de todos os pedidos; 6) ache o pedido de maior frete; 7) salve "
            "fretes_L03.csv com o cabeçalho id,uf,regiao,frete e uma linha por pedido em ordem de id; "
            "8) responda com o frete total e o id do pedido de maior frete.")]),
        "L04": Fixture("L04", "Duas páginas encadeadas + uma que não existe", [], [Turno(
            f"1) Leia o catálogo em {p}/L04_catalogo.md; 2) leia preços e estoque em {p}/L04_precos.md; "
            f"3) tente ler as promoções em {p}/L04_promocoes.md — se falhar, siga sem promoção e diga isso "
            "na resposta; 4) junte catálogo e preços pelo código; 5) separe os itens com estoque 0; "
            "6) para os outros, calcule valor em estoque = preço × estoque; 7) some por categoria, com 2 "
            "casas; 8) salve estoque_L04.json exatamente no formato "
            '{"categorias":{"Categoria":0.00},"itens_sem_estoque":["código"]}; 9) guarde na memória o fato '
            '"Categoria de maior valor em estoque (L04): <categoria>"; 10) responda com a categoria de maior '
            "valor e se as promoções foram lidas ou não.")]),
        "L05": Fixture("L05", "MCP: reposição com erro temporário e registro com efeito", [], [Turno(
            "Use as ferramentas do conector bancada: 1) leia o estoque; 2) para cada item com quantidade "
            "abaixo do mínimo, calcule quanto falta para chegar ao DOBRO do mínimo; 3) consulte o preço de "
            "cada um desses itens (se der erro temporário, tente de novo uma vez); 4) registre um pedido de "
            "compra por item com a quantidade calculada; 5) leia os pedidos registrados para conferir que "
            "não ficou nada repetido nem faltando; 6) salve compras_L05.csv com o cabeçalho "
            "sku,quantidade,preco_unitario,subtotal, uma linha por item e uma última linha TOTAL com a soma "
            "no subtotal; 7) responda com o total da compra.")], usa_mcp=True,
            cartao_esperado="registrar_pedido_compra (revisor) → se abrir cartão, Permitir uma vez"),
        "L06": Fixture("L06", "MCP: erro permanente sem inventar valor", [], [Turno(
            "Calcule o frete destes 5 CEPs com a ferramenta de frete do conector bancada: 01310-100, "
            "20040-002, 30130-010, 69900-000, 80010-000. 1) consulte cada CEP; 2) se algum falhar, tente "
            "mais uma vez; 3) se continuar falhando, marque como INDISPONIVEL (não estime nenhum valor); "
            "4) some só os fretes que deram certo, com 2 casas; 5) ache o CEP de frete mais caro; 6) salve "
            'fretes_L06.json exatamente no formato {"fretes":{"CEP":0.00 ou "INDISPONIVEL"},"soma":0.00,'
            '"mais_caro":"CEP"}; 7) adicione a pendência "Refazer frete do CEP 69900-000"; 8) responda com '
            "a soma e qual CEP ficou indisponível.")], usa_mcp=True),
        "L07": Fixture("L07", "Envio recusado → salvar local e pendência", ["relatorio_L07.csv"], [Turno(
            "Monte o relatório semanal a partir do anexo relatorio_L07.csv: 1) leia o arquivo; 2) some os "
            "atendimentos por dia; 3) ache o dia com mais atendimentos; 4) calcule a média diária com 1 "
            "casa; 5) escreva um texto curto com esses números; 6) envie o texto pela ferramenta "
            "enviar_relatorio do conector bancada para financeiro@exemplo.com.br com o assunto "
            "'Relatório semanal L07'; 7) se o envio for recusado, NÃO envie de outro jeito: salve o texto "
            "em relatorio_L07.md e me avise que ficou salvo; 8) adicione a pendência "
            '"Enviar relatório L07 depois"; 9) responda com o dia de mais atendimentos.',
            decisao_cartao="negar")], usa_mcp=True,
            cartao_esperado="enviar_relatorio (envio) → cartão obrigatório → Recusar"),
        "L08": Fixture("L08", "Pergunta no meio + pendências", [], [Turno(
            "Organize as tarefas da mudança de escritório. Antes de começar, me pergunte (com a ferramenta "
            "de pergunta) se a mudança é no sábado ou no domingo. Depois: 1) crie estas 5 pendências: "
            "'Contratar caminhão', 'Embalar arquivos', 'Desligar internet antiga', 'Ligar internet nova', "
            "'Avisar clientes'; 2) nas notas da pendência 'Contratar caminhão', anote o dia que eu escolhi; "
            "3) conclua 'Embalar arquivos'; 4) remova 'Desligar internet antiga' (não precisa mais); "
            "5) liste as pendências abertas; 6) salve mudanca_L08.md com as pendências abertas, uma por "
            "linha, em ordem alfabética; 7) responda quantas ficaram abertas.",
            resposta_pergunta=D.L08_RESPOSTA)], cartao_esperado="perguntar → responder 'domingo'"),
        "L09": Fixture("L09", "Agenda: criar, cancelar, recriar e conferir", [], [Turno(
            "Crie estes lembretes (fuso de São Paulo): 1) 'Treinamento módulo 1' em 08/02/2027 às 09:00; "
            "2) 'Treinamento módulo 2' em 15/02/2027 às 09:00; 3) 'Treinamento módulo 3' em 22/02/2027 às "
            "09:00; 4) 'Revisão geral' recorrente todo ano em 29 de fevereiro às 08:30 (cron 30 8 29 2 *); "
            "5) liste os agendamentos; 6) cancele o 'Treinamento módulo 2' (foi adiado); 7) crie "
            "'Treinamento módulo 2' de novo em 01/03/2027 às 09:00; 8) liste de novo para conferir; "
            "9) guarde na memória o fato 'Treinamento L09 termina em 01/03/2027'; 10) salve agenda_L09.md "
            "com os agendamentos ativos, um por linha; 11) responda quantos agendamentos ativos ficaram.")]),
        "L10": Fixture("L10", "Planilha de 3 abas, correção no 2º turno, habilidade aprovada",
                       ["orcamento_L10.xlsx"], [
            Turno("Anexei orcamento_L10.xlsx (abas Receitas, Despesas e Metas). 1) leia a planilha; 2) some "
                  "as receitas de cada mês (jan, fev, mar); 3) some as despesas de cada mês; 4) calcule o "
                  "saldo de cada mês (receitas − despesas); 5) compare com a meta de saldo do mês (aba "
                  "Metas); 6) salve saldo_L10.csv com o cabeçalho mes,receitas,despesas,saldo,meta,atingiu "
                  "(atingiu = sim se saldo ≥ meta, senão nao), uma linha por mês; 7) guarde na memória o fato "
                  "'Pior mês de saldo (L10): <mês>'; 8) responda com o pior mês."),
            Turno("Correção: o Aluguel de fevereiro foi lançado em dobro; considere só a metade dele. "
                  "1) refaça as contas de fevereiro; 2) salve saldo_L10_v2.csv no mesmo formato, com os três "
                  "meses; 3) se o pior mês mudou, apague a memória antiga do pior mês e guarde a nova; "
                  "4) crie uma habilidade chamada saldo-mensal com o passo a passo que você usou (isso vai "
                  "pedir minha aprovação); 5) responda com o saldo corrigido de fevereiro e o pior mês agora."),
        ], cartao_esperado="esquecer_memoria e criar_habilidade (cartões fixos) → Permitir uma vez"),
    }


FIXTURES = _fixtures()


# ------------------------------------------------------------------------------- utilidades
def ler_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for linha in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def agora() -> datetime:
    return datetime.now(UTC)


def num(valor: Any) -> Decimal | None:
    if valor is None:
        return None
    if isinstance(valor, (int, float, Decimal)):
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    texto = str(valor).replace("R$", "").replace(" ", "").strip()
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def sem_acento(texto: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


class Api:
    def __init__(self, token: str | None = None) -> None:
        self.c = httpx.AsyncClient(base_url=API + "/v1", timeout=60)
        self.token = token

    def _h(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def req(self, metodo: str, caminho: str, **kw) -> httpx.Response:
        return await self.c.request(metodo, caminho, headers=self._h(), **kw)

    async def json(self, metodo: str, caminho: str, esperado: int | tuple = 200, **kw) -> Any:
        r = await self.req(metodo, caminho, **kw)
        ok = (r.status_code in esperado) if isinstance(esperado, tuple) else r.status_code == esperado
        if not ok:
            raise RuntimeError(f"{metodo} {caminho} → {r.status_code} {r.text[:300]}")
        return r.json() if r.content else None

    async def fechar(self) -> None:
        await self.c.aclose()


async def entrar() -> tuple[Api, dict]:
    est = json.loads(ESTADO.read_text("utf-8"))
    api = Api()
    dados = await api.json("POST", "/auth/entrar", json={"email": est["email"], "senha": SENHA_QA})
    api.token = dados["token_acesso"]
    return api, est


# ------------------------------------------------------------------------------- preparar / modelos
async def preparar() -> None:
    env = ler_env()
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    est = json.loads(ESTADO.read_text("utf-8")) if ESTADO.exists() else {}
    api = Api()
    if "email" not in est:
        codigo = f"BASE-{int(time.time()):X}"
        subprocess.run(["uv", "run", "python", "-m", "app.cli", "convite", "criar", "--codigo", codigo,
                        "--usos", "1"], cwd=BACKEND, check=True, capture_output=True,
                       env={**os.environ, "AMBIENTE": "desenvolvimento"})
        est["email"] = f"baseline-05-{int(time.time())}@bancada.local"
        await api.json("POST", "/auth/cadastrar", 201, json={"nome": "Baseline 0.5", "email": est["email"],
                                                              "senha": SENHA_QA, "convite": codigo})
        ESTADO.write_text(json.dumps(est), "utf-8")
    api, est = await entrar()
    if est.get("provedor_tipo", "groq") != TIPO_PROVEDOR:  # troca de modelo fixo: guarda o anterior
        est.setdefault("historico", []).append({k: est.pop(k) for k in ("provedor_id", "modelo_id") if k in est})
    existentes = [p for p in await api.json("GET", "/provedores") if p.get("tipo") == TIPO_PROVEDOR]
    if not existentes:
        if TIPO_PROVEDOR != "groq":
            # A conexão google da bancada foi copiada da conta do Heitor por um script de uso único
            # (baseline.md §2); este executor nunca vê nem grava essa chave.
            sys.exit(f"A conta de bancada não tem conexão {TIPO_PROVEDOR}. Veja baseline.md §2.")
        await api.json("POST", "/provedores", 201, json={"tipo": "groq", "chave": env["SORA_QA_GROQ_CHAVE"]})
        existentes = [p for p in await api.json("GET", "/provedores") if p.get("tipo") == "groq"]
    est["provedor_id"] = existentes[0].get("id") or existentes[0].get("provedor_id")
    est["provedor_tipo"] = TIPO_PROVEDOR
    modelos = await api.json("GET", "/modelos")
    alvo = next((m for m in modelos if m["modelo"] == MODELO_FIXO), None)
    if alvo is None:
        alvo = await api.json("POST", f"/provedores/{est['provedor_id']}/modelos", 201, json={"id": MODELO_ID_PROVEDOR})
    # Visão e ferramentas foram provadas por chamada direta (imagem + ferramenta, baseline.md §2); se o
    # catálogo não as marca, o dono marca as capacidades (CLAUDE.md §7.3).
    caps = sorted(set(alvo.get("capacidades") or []) | {"ferramentas", "json", "visao"})
    await api.json("PATCH", f"/modelos/{alvo['id']}", json={"capacidades": caps, "ativo": True})
    desligados = []
    for m in await api.json("GET", "/modelos"):
        if m["modelo"] != MODELO_FIXO and m.get("ativo"):
            await api.json("PATCH", f"/modelos/{m['id']}", json={"ativo": False})
            desligados.append(m["modelo"])
    est["modelo_id"] = alvo["id"]
    est["reservas_desligadas"] = desligados
    conectores = await api.json("GET", "/conectores")
    if not any(c["nome"] == "bancada" for c in conectores):
        c = await api.json("POST", "/conectores", 201, json={
            "nome": "bancada", "url": f"http://127.0.0.1:{PORTA_MCP}/mcp",
            "cabecalhos": {"Authorization": "Bearer bancada-local"}})
        est["conector_id"] = c["id"]
    ESTADO.write_text(json.dumps(est, indent=1), "utf-8")
    print("conta:", est["email"], "| provedor:", est["provedor_id"], "| modelo fixo:", MODELO_FIXO)
    print("reservas desligadas:", desligados or "nenhuma")
    await api.fechar()


async def limpar_bots() -> None:
    """Apaga (exclusão lógica, pela API) todos os bots individuais da conta de bancada. A Sora fica."""
    api, est = await entrar()
    apagados = 0
    for a in await api.json("GET", "/agentes"):
        if a.get("tipo", "individual") == "individual" and a.get("nome") != "Sora":
            r = await api.req("DELETE", f"/agentes/{a['id']}")
            apagados += r.status_code == 204
    est.pop("bot_pc_id", None)
    ESTADO.write_text(json.dumps(est, indent=1), "utf-8")
    restantes = [a.get("nome") for a in await api.json("GET", "/agentes")]
    print(f"bots apagados: {apagados} | restantes: {restantes}")
    await api.fechar()


async def listar_modelos() -> None:
    api, _ = await entrar()
    for p in await api.json("GET", "/provedores"):
        print("provedor", p.get("id"), p.get("tipo"), p.get("nome"), "| estado:", p.get("estado") or p.get("status"))
    for m in await api.json("GET", "/modelos"):
        print(f"  {m['modelo']:45} ativo={m.get('ativo')} nivel={m.get('nivel')} cap={m.get('capacidades')}")
    await api.fechar()


# ------------------------------------------------------------------------------- SSE e turnos
class Ouvinte:
    def __init__(self, api: Api, conversa_id: str) -> None:
        self.api, self.conversa_id = api, conversa_id
        self.eventos: list[dict] = []
        self.t0 = time.monotonic()
        self.tarefa = asyncio.create_task(self._ler())

    async def _ler(self) -> None:
        url = f"{API}/v1/conversas/{self.conversa_id}/eventos"
        try:
            async with httpx.AsyncClient(timeout=None) as c, c.stream(
                "GET", url, headers={**self.api._h(), "Accept": "text/event-stream"}) as r:
                nome, dados = "message", []
                async for linha in r.aiter_lines():
                    if linha == "":
                        if dados and nome != "ping":
                            try:
                                d = json.loads("\n".join(dados))
                            except ValueError:
                                d = "\n".join(dados)
                            self.eventos.append({"t": round(time.monotonic() - self.t0, 2), "ev": nome, "d": d})
                        nome, dados = "message", []
                    elif linha.startswith("event:"):
                        nome = linha[6:].strip()
                    elif linha.startswith("data:"):
                        dados.append(linha[5:].strip())
        except (httpx.HTTPError, asyncio.CancelledError) as erro:
            if not isinstance(erro, asyncio.CancelledError):
                self.eventos.append({"t": round(time.monotonic() - self.t0, 2), "ev": "_erro_sse", "d": str(erro)})

    def fechar(self) -> None:
        self.tarefa.cancel()


async def _estado_bot(api: Api, bot_id: str) -> str:
    for a in await api.json("GET", "/agentes"):
        if a["id"] == bot_id:
            return a.get("estado", "livre")
    return "?"


async def rodar_turno(api: Api, ouv: Ouvinte, bot_id: str, turno: Turno, inicio_ev: int, reg: dict) -> dict:
    """Espera o turno acabar, decidindo cartões e perguntas como o usuário faria."""
    t0 = time.monotonic()
    vistos: set[str] = set()
    ultimo_evento = time.monotonic()
    n_antes = len(ouv.eventos)
    fim_visto = False
    autores: dict[str, str] = {}
    while time.monotonic() - t0 < PRAZO_TURNO_S:
        await asyncio.sleep(2)
        if len(ouv.eventos) != n_antes:
            n_antes, ultimo_evento = len(ouv.eventos), time.monotonic()
        for e in ouv.eventos[inicio_ev:]:
            d = e["d"] if isinstance(e["d"], dict) else {}
            if e["ev"] == "pergunta" and d.get("pergunta_id") not in vistos:
                vistos.add(d["pergunta_id"])
                valor = turno.resposta_pergunta or "sim"
                for op in d.get("opcoes") or []:
                    if sem_acento(valor) in sem_acento(f"{op.get('rotulo', '')} {op.get('valor', '')}"):
                        valor = op["valor"]
                        break
                await asyncio.sleep(2)
                r = await api.req("POST", f"/perguntas/{d['pergunta_id']}/responder", json={"valor": valor})
                reg["perguntas"].append({"texto": d.get("texto"), "resposta": valor, "http": r.status_code})
            if e["ev"] == "aprovacao.pedida" and d.get("aprovacao_id") not in vistos:
                vistos.add(d["aprovacao_id"])
                await asyncio.sleep(2)
                r = await api.req("POST", f"/aprovacoes/{d['aprovacao_id']}/decidir",
                                  json={"decisao": turno.decisao_cartao})
                reg["cartoes"].append({"resumo": d.get("resumo"), "decisao": turno.decisao_cartao, "http": r.status_code})
            if e["ev"] == "mensagem.inicio":
                autores[str(d.get("mensagem_id"))] = str(d.get("autor"))
            if e["ev"] == "mensagem.fim" and autores.get(str(d.get("mensagem_id")), "?") != "usuario":
                fim_visto = True
        if fim_visto and time.monotonic() - ultimo_evento > 8:
            if await _estado_bot(api, bot_id) != "trabalhando":
                return {"terminou": True, "segundos": round(time.monotonic() - t0, 1)}
    return {"terminou": False, "segundos": round(time.monotonic() - t0, 1),
            "estado_bot": await _estado_bot(api, bot_id)}


# ------------------------------------------------------------------------------- provas
async def sql(consulta: str, **params) -> list[dict]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    motor = create_async_engine(ler_env()["DATABASE_URL"])
    try:
        async with motor.connect() as con:
            linhas = (await con.execute(text(consulta), params)).mappings().all()
            return [dict(x) for x in linhas]
    finally:
        await motor.dispose()


async def coletar(api: Api, est: dict, conversa_id: str, bot_id: str, t0: datetime, t1: datetime,
                  log_worker: Path | None) -> dict:
    msgs = await api.json("GET", f"/conversas/{conversa_id}/mensagens", params={"limite": 100})
    msgs = msgs if isinstance(msgs, list) else msgs.get("itens", [])
    arquivos: dict[str, str] = {}
    for m in msgs:
        if m.get("autor") == "usuario":
            continue
        for a in m.get("anexos") or []:
            aid = a.get("anexo_id") or a.get("id") if isinstance(a, dict) else a
            nome = a.get("nome") if isinstance(a, dict) else None
            r = await api.req("GET", f"/anexos/{aid}")
            if r.status_code == 200:
                if not nome:
                    nome = re.findall(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', r.headers.get("content-disposition", "")) or [str(aid)]
                    nome = nome[0]
                arquivos[nome] = r.content.decode("utf-8", errors="replace") if not str(nome).endswith(".xlsx") else "<xlsx>"
    u = est["usuario_id"]
    chamadas = await sql("SELECT papel, modelo, tokens_entrada, tokens_saida, custo_usd, latencia_ms FROM chamadas_modelo "
                         "WHERE usuario_id = :u AND criado_em BETWEEN :a AND :b ORDER BY criado_em", u=u, a=t0, b=t1)
    passos = await sql("SELECT tipo::text AS tipo, ferramenta, status, texto FROM passos WHERE agente_id = :g "
                       "ORDER BY iniciado_em", g=bot_id)
    rastro = {"modelo.pedido": 0, "ferramenta.inicio": 0, "modelo.erro": 0, "ferramenta.erro": 0, "ferramenta.pausa": 0,
              "erros_de_limite": 0, "ferramentas": [], "erros_modelo_por_tipo": {}}
    if log_worker and log_worker.exists():
        for linha in log_worker.read_text("utf-8", errors="replace").splitlines():
            if conversa_id in linha and '"evento"' in linha:
                m = re.search(r'"evento":\s*"([^"]+)"', linha)
                if m and m.group(1) in rastro:
                    rastro[m.group(1)] += 1
                if '"RateLimitError"' in linha:
                    rastro["erros_de_limite"] += 1
                if m and m.group(1) == "modelo.erro":
                    tipo = re.search(r'"tipo":\s*"([^"]+)"', linha)
                    chave = tipo.group(1) if tipo else "?"
                    rastro["erros_modelo_por_tipo"][chave] = rastro["erros_modelo_por_tipo"].get(chave, 0) + 1
                if m and m.group(1) == "ferramenta.inicio":
                    nome = re.search(r'"nome":\s*"([^"]+)"', linha)
                    rastro["ferramentas"].append(nome.group(1) if nome else "?")
    return {
        "mensagens": [{"autor": m.get("autor"), "conteudo": (m.get("conteudo") or "")[:1500], "estado": m.get("estado")} for m in msgs],
        "arquivos": arquivos,
        "chamadas_modelo": chamadas,
        "passos": passos,
        "rastro": rastro,
        "memorias": await sql("SELECT conteudo FROM memorias WHERE agente_id = :g", g=bot_id),
        "pendencias": await sql("SELECT titulo, notas, status FROM pendencias WHERE agente_id = :g", g=bot_id),
        "rotinas": await sql("SELECT titulo, tipo, expressao, fuso, proxima_execucao::text AS proxima, ativa FROM rotinas "
                             "WHERE agente_id = :g", g=bot_id),
        "habilidades": await sql("SELECT nome, descricao FROM habilidades WHERE usuario_id = :u AND criada_em >= :a", u=u, a=t0),
        "aprovacoes": await sql("SELECT acao::text AS acao, status::text AS status FROM aprovacoes "
                                "WHERE agente_id = :g ORDER BY criado_em", g=bot_id),
    }


def _arquivo(prova: dict, nome: str) -> str | None:
    for k, v in prova["arquivos"].items():
        if k.lower() == nome.lower():
            return v
    return None


def _csv_linhas(texto: str) -> list[dict]:
    texto = texto.strip().lstrip("﻿")
    sep = ";" if texto.splitlines()[0].count(";") > texto.splitlines()[0].count(",") else ","
    return [{k.strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(texto), delimiter=sep)]


def _json_de(texto: str | None) -> Any:
    if texto is None:
        return None
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    try:
        return json.loads(texto)
    except ValueError:
        return None


def _resposta(prova: dict) -> str:
    textos = [m["conteudo"] for m in prova["mensagens"] if m["autor"] != "usuario"]
    return textos[-1] if textos else ""


def conferir(fid: str, prova: dict, mcp: dict) -> tuple[list[tuple[str, bool]], str]:
    """Lista de (critério, passou) e um texto curto de prova."""
    g = D.GABARITOS[fid]()
    ck: list[tuple[str, bool]] = []
    resp = sem_acento(_resposta(prova))
    mems = " | ".join(sem_acento(m["conteudo"]) for m in prova["memorias"])
    if fid == "L01":
        j = _json_de(_arquivo(prova, "resumo_L01.json"))
        ck.append(("arquivo resumo_L01.json é JSON", isinstance(j, dict)))
        if isinstance(j, dict):
            lojas = [(sem_acento(str(x.get("loja", ""))), num(x.get("total"))) for x in j.get("lojas", [])]
            ck.append(("lojas e totais na ordem", lojas == [(sem_acento(x["loja"]), x["total"]) for x in g["lojas"]]))
            ck.append(("média", num(j.get("media")) == g["media"]))
            ck.append(("devoluções descartadas", j.get("devolucoes_descartadas") == g["devolucoes_descartadas"]))
        ck.append(("memória com a campeã", "l01" in mems and "praia" in mems))
        ck.append(("resposta com campeã e total", "praia" in resp and re.search(r"1\.?005[,.]6", resp) is not None))
    elif fid == "L02":
        ipe = [m for m in prova["memorias"] if "ipe" in sem_acento(m["conteudo"])]
        ck.append(("5 memórias do Ipê", len(ipe) == 5))
        ck.append(("Bianca guardada", any("bianca" in sem_acento(m["conteudo"]) for m in ipe)))
        ck.append(("Caio apagado", not any("caio" in sem_acento(m["conteudo"]) for m in ipe)))
        ck.append(("cartão de esquecer_memoria aberto", any("esquecer_memoria" in a["acao"] for a in prova["aprovacoes"])))
        arq = _arquivo(prova, "ipe_L02.md") or ""
        campos = {sem_acento(k.strip(" -*")): v.strip() for k, _, v in (ln.partition(":") for ln in arq.splitlines()) if v}
        ck.append(("arquivo: responsável Bianca", "bianca" in sem_acento(campos.get("responsavel", ""))))
        ck.append(("arquivo: dias_ate_prazo = 56", re.sub(r"\D", "", campos.get("dias_ate_prazo", "")) == str(g["dias_ate_prazo"])))
        ck.append(("arquivo: cliente/orçamento/prazo/cor", all(sem_acento(str(g[c])).replace("r$ ", "") in sem_acento(campos.get(c, "")).replace("r$ ", "")
                                                              for c in ("cliente", "prazo", "cor")) and "18" in campos.get("orcamento", "")))
        ck.append(("resposta: Bianca", "bianca" in resp))
    elif fid == "L03":
        arq = _arquivo(prova, "fretes_L03.csv")
        ck.append(("arquivo fretes_L03.csv", arq is not None))
        if arq:
            linhas = _csv_linhas(arq)
            obtido = [(str(r.get("id")), r.get("uf", "").upper(), sem_acento(r.get("regiao", "")), num(r.get("frete"))) for r in linhas]
            esperado = [(str(x["id"]), x["uf"], sem_acento(x["regiao"]), x["frete"]) for x in g["linhas"]]
            ck.append(("8 linhas na ordem e valores", obtido == esperado))
            certos = sum(1 for a, b in zip(obtido, esperado, strict=False) if a == b)
            ck.append((f"linhas certas {certos}/8", certos >= 6))
        ck.append(("resposta: total 172,07 e id 305", ("172.07" in resp or "172,07" in resp) and "305" in resp))
    elif fid == "L04":
        j = _json_de(_arquivo(prova, "estoque_L04.json"))
        ck.append(("arquivo estoque_L04.json é JSON", isinstance(j, dict)))
        if isinstance(j, dict):
            cats = {sem_acento(k): num(v) for k, v in (j.get("categorias") or {}).items()}
            ck.append(("totais por categoria", cats == {sem_acento(k): v for k, v in g["categorias"].items()}))
            ck.append(("itens sem estoque", sorted(map(str, j.get("itens_sem_estoque") or [])) == g["itens_sem_estoque"]))
        ck.append(("memória: Mercearia", "l04" in mems and "mercearia" in mems))
        ck.append(("resposta: promoções não lidas", "promo" in resp and any(x in resp for x in ("nao", "falh", "indispon", "erro", "404", "existe"))))
        ck.append(("resposta: Mercearia", "mercearia" in resp))
    elif fid == "L05":
        pedidos = mcp.get("pedidos", [])
        obt = sorted((p["sku"], p["quantidade"]) for p in pedidos)
        esp = sorted((i["sku"], i["quantidade"]) for i in g["itens"])
        ck.append(("MCP: pedidos exatamente os esperados (sem repetição)", obt == esp))
        ck.append(("MCP: P-03 consultado de novo após o erro", sum(1 for c in mcp.get("chamadas", []) if c["ferramenta"] == "consultar_preco" and c["argumentos"].get("sku") == "P-03") >= 2))
        ck.append(("MCP: conferiu os pedidos", any(c["ferramenta"] == "ler_pedidos_registrados" for c in mcp.get("chamadas", []))))
        arq = _arquivo(prova, "compras_L05.csv")
        ok_arq = False
        if arq:
            linhas = _csv_linhas(arq)
            itens = [(r.get("sku", "").upper(), num(r.get("quantidade")), num(r.get("preco_unitario")), num(r.get("subtotal"))) for r in linhas if r.get("sku", "").upper() != "TOTAL"]
            total = [num(r.get("subtotal")) for r in linhas if r.get("sku", "").upper() == "TOTAL"]
            ok_arq = sorted(itens) == sorted((i["sku"], num(i["quantidade"]), i["preco_unitario"], i["subtotal"]) for i in g["itens"]) and total == [g["total"]]
        ck.append(("arquivo compras_L05.csv com itens e TOTAL", ok_arq))
        ck.append(("resposta: 270,75", "270.75" in resp or "270,75" in resp))
    elif fid == "L06":
        j = _json_de(_arquivo(prova, "fretes_L06.json"))
        ck.append(("arquivo fretes_L06.json é JSON", isinstance(j, dict)))
        if isinstance(j, dict):
            fr = {k: (v if isinstance(v, str) and not num(v) else num(v)) for k, v in (j.get("fretes") or {}).items()}
            ck.append(("69900-000 marcado INDISPONIVEL (sem valor inventado)", str(fr.get("69900-000", "")).upper().startswith("INDISPON")))
            ck.append(("4 fretes certos", all(fr.get(k) == v for k, v in g["fretes"].items() if v != "INDISPONIVEL")))
            ck.append(("soma 84,55", num(j.get("soma")) == g["soma"]))
            ck.append(("mais caro 80010-000", j.get("mais_caro") == g["mais_caro"]))
        ck.append(("MCP: CEP com falha tentado 2 vezes", sum(1 for c in mcp.get("chamadas", []) if c["ferramenta"] == "consultar_frete" and c["argumentos"].get("cep") == "69900-000") >= 2))
        ck.append(("pendência criada", any("69900" in p["titulo"] for p in prova["pendencias"])))
        ck.append(("resposta: soma e CEP indisponível", ("84.55" in resp or "84,55" in resp) and "69900" in resp))
    elif fid == "L07":
        ck.append(("MCP: nada enviado (cartão recusado)", not mcp.get("enviados")))
        ck.append(("cartão de envio aberto", any("enviar_relatorio" in a["acao"] for a in prova["aprovacoes"])))
        arq = _arquivo(prova, "relatorio_L07.md") or ""
        ck.append(("arquivo relatorio_L07.md com sexta, 29 e 24,0", "sexta" in sem_acento(arq) and "29" in arq and ("24.0" in arq or "24,0" in arq or "24 " in arq)))
        ck.append(("pendência criada", any("l07" in sem_acento(p["titulo"]) for p in prova["pendencias"])))
        ck.append(("resposta: sexta", "sexta" in resp))
    elif fid == "L08":
        abertas = sorted(p["titulo"] for p in prova["pendencias"] if p["status"] in ("aberta", "estacionada"))
        ck.append(("pergunta feita e respondida", bool(prova.get("perguntas"))))
        ck.append(("pendências abertas certas", [sem_acento(x) for x in abertas] == [sem_acento(x) for x in g["abertas"]]))
        cam = next((p for p in prova["pendencias"] if "caminhao" in sem_acento(p["titulo"])), None)
        ck.append(("notas do caminhão com domingo", bool(cam) and "domingo" in sem_acento(cam["notas"] or "")))
        emb = next((p for p in prova["pendencias"] if "embalar" in sem_acento(p["titulo"])), None)
        ck.append(("Embalar arquivos concluída", bool(emb) and emb["status"] == "concluida"))
        arq = _arquivo(prova, "mudanca_L08.md") or ""
        linhas = [sem_acento(re.sub(r"^[\s\-*\d.)\[\]x]+", "", x)).strip() for x in arq.splitlines() if x.strip()]
        ck.append(("arquivo com as 3 abertas em ordem alfabética", [x for x in linhas if x] == [sem_acento(x) for x in g["abertas"]]))
        ck.append(("resposta: 3", re.search(r"\b3\b|tres", resp) is not None))
    elif fid == "L09":
        ativos = {sem_acento(r["titulo"]): r for r in prova["rotinas"] if r["ativa"]}
        ck.append(("4 agendamentos ativos com os títulos certos", sorted(ativos) == sorted(sem_acento(t) for t in g["ativos"])))
        m2 = ativos.get(sem_acento("Treinamento módulo 2"))
        ck.append(("módulo 2 remarcado para 01/03/2027", bool(m2) and "2027-03-01" in (m2["proxima"] or "")))
        ck.append(("módulo 2 antigo cancelado", any(sem_acento(r["titulo"]) == sem_acento("Treinamento módulo 2") and not r["ativa"] for r in prova["rotinas"])))
        rev = ativos.get(sem_acento("Revisão geral"))
        ck.append(("Revisão geral recorrente 29/02 08:30", bool(rev) and (rev["expressao"] or "").split() == "30 8 29 2 *".split()))
        ck.append(("memória do fim do treinamento", "l09" in mems and ("2027-03-01" in mems or "01/03/2027" in mems)))
        ck.append(("arquivo agenda_L09.md", _arquivo(prova, "agenda_L09.md") is not None))
        ck.append(("resposta: 4", re.search(r"\b4\b|quatro", resp) is not None))
    elif fid == "L10":
        for nome, chave in (("saldo_L10.csv", "v1"), ("saldo_L10_v2.csv", "v2")):
            arq = _arquivo(prova, nome)
            ok = False
            if arq:
                linhas = _csv_linhas(arq)
                obt = [(sem_acento(r.get("mes", ""))[:3], num(r.get("receitas")), num(r.get("despesas")), num(r.get("saldo")), num(r.get("meta")), sem_acento(r.get("atingiu", ""))) for r in linhas]
                esp = [(x["mes"], x["receitas"], x["despesas"], x["saldo"], x["meta"], x["atingiu"]) for x in g[chave]["linhas"]]
                ok = obt == esp
            ck.append((f"arquivo {nome} confere", ok))
        l10 = [sem_acento(m["conteudo"]) for m in prova["memorias"] if "l10" in sem_acento(m["conteudo"])]
        ck.append(("memória do pior mês = março (antiga apagada)", bool(l10) and all("mar" in m and "fev" not in m for m in l10)))
        ck.append(("cartões de esquecer_memoria e criar_habilidade", all(any(f in a["acao"] for a in prova["aprovacoes"]) for f in ("esquecer_memoria", "criar_habilidade"))))
        ck.append(("habilidade saldo-mensal criada", any(sem_acento(h["nome"]).replace(" ", "-") == "saldo-mensal" for h in prova["habilidades"])))
        ck.append(("resposta: 3.900 e março", ("3900" in resp.replace(".", "").replace(",", "")) and "mar" in resp))
    texto = "; ".join(f"{'✔' if ok else '✘'} {nome}" for nome, ok in ck)
    return ck, texto


COTA = ("limite de uso do provedor", "tempo deste turno acabou", "limite do provedor", "excede o limite deste modelo",
        "cota diaria deste modelo", "limite por minuto do plano")


def por_cota(prova: dict) -> bool:
    """Parou pelo limite do plano do provedor (429/413 da Groq gratuita): 'não executado', não é falha do produto."""
    final = sem_acento(_resposta(prova))
    return prova["rastro"].get("erros_de_limite", 0) > 0 and any(sem_acento(x) in final for x in COTA)


def classificar(ck: list[tuple[str, bool]], reg: dict, prova: dict) -> tuple[str, str]:
    passou = sum(1 for _, ok in ck if ok)
    resultado = "ok" if passou == len(ck) else ("parcial" if passou > 0 else "falhou")
    if resultado != "ok" and por_cota(prova):
        return "nao_executado", "cota_provedor"
    if not all(t.get("terminou") for t in reg["turnos"]):
        return resultado if resultado != "ok" else "parcial", "estado" if any(t.get("estado_bot") == "trabalhando" for t in reg["turnos"]) else "prazo"
    if resultado == "ok":
        return resultado, ""
    textos = " ".join(sem_acento(str(p.get("texto", ""))) for p in prova["passos"]) + " " + " ".join(sem_acento(m["conteudo"]) for m in prova["mensagens"])
    if any(x in textos for x in ("limite de passos", "limite de chamadas", "orcamento")):
        return resultado, "orcamento"
    if any(x in textos for x in ("is not a valid tool", "argumentos invalidos", "validation error", "json")) and prova["rastro"].get("ferramenta.erro"):
        return resultado, "schema"
    if any("cartão" in n or "cartao" in n or "pergunta" in n for n, ok in ck if not ok):
        return resultado, "aprovacao"
    return resultado, "modelo"


# ------------------------------------------------------------------------------- uma execução
async def executar(fid: str, rodada: int, log_worker: Path | None) -> dict:
    fx = FIXTURES[fid]
    marca = agora().strftime("%Y%m%dT%H%M%S")
    pasta = EXECUCOES / f"{fid}-r{rodada}-{marca}"
    pasta.mkdir(parents=True, exist_ok=True)
    servidor = subprocess.Popen([sys.executable, str(AQUI / "mcp_bancada.py"), str(PORTA_MCP), str(pasta / "mcp")],
                                cwd=BACKEND, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(3)
    api, est = await entrar()
    reg: dict[str, Any] = {"tarefa": fid, "rodada": rodada, "inicio": agora().isoformat(), "modelo_fixo": MODELO_FIXO,
                           "turnos": [], "cartoes": [], "perguntas": []}
    try:
        if "usuario_id" not in est:
            est["usuario_id"] = (await sql("SELECT id::text AS id FROM usuarios WHERE email = :e", e=est["email"]))[0]["id"]
            ESTADO.write_text(json.dumps(est, indent=1), "utf-8")
        bot = await api.json("POST", "/agentes", 201, json={"nome": f"Bancada{fid}r{rodada}{marca[-4:]}",
                                                             "funcao": "Bot de bancada (baseline 0.5)",
                                                             "papel": PAPEL_BOT, "ferramentas": FERRAMENTAS_BOT})
        await api.json("PATCH", f"/agentes/{bot['id']}", json={"provedor_id": est["provedor_id"], "modelo": MODELO_FIXO,
                                                                "raciocinio": "auto", "permissao": "perguntar"})
        reg["bot_id"] = bot["id"]
        anexos = []
        for nome in fx.anexos:
            caminho = RAIZ / "dados" / nome
            r = await api.req("POST", "/anexos", files={"arquivo": (nome, caminho.read_bytes())})
            if r.status_code != 201:
                raise RuntimeError(f"anexo {nome}: {r.status_code} {r.text[:200]}")
            anexos.append(r.json()["anexo_id"])
        t0 = agora()
        conversa = await api.json("POST", "/conversas", 201, json={"agente_id": bot["id"], "texto": fx.turnos[0].texto, "anexos": anexos})
        reg["conversa_id"] = conversa["id"]
        ouv = Ouvinte(api, conversa["id"])
        for i, turno in enumerate(fx.turnos):
            inicio = len(ouv.eventos)
            if i > 0:
                await api.json("POST", f"/conversas/{conversa['id']}/mensagens", 202, json={"texto": turno.texto, "anexos": []})
            reg["turnos"].append(await rodar_turno(api, ouv, bot["id"], turno, inicio, reg))
        await asyncio.sleep(3)
        t1 = agora()
        ouv.fechar()
        prova = await coletar(api, est, conversa["id"], bot["id"], t0, t1, log_worker)
        prova["perguntas"] = reg["perguntas"]
        mcp = {}
        for nome in ("pedidos.json", "enviados.json"):
            arq = pasta / "mcp" / nome
            mcp[nome.split(".")[0]] = json.loads(arq.read_text("utf-8")) if arq.exists() else []
        cham = pasta / "mcp" / "chamadas.jsonl"
        mcp["chamadas"] = [json.loads(x) for x in cham.read_text("utf-8").splitlines()] if cham.exists() else []
        ck, texto = conferir(fid, prova, mcp)
        resultado, classe = classificar(ck, reg, prova)
        limite = [e for e in ouv.eventos if e["ev"] == "passo" and isinstance(e["d"], dict)
                  and (e["d"].get("parametros") or {}).get("motivo") == "limite_de_taxa"]
        reg.update({
            "fim": t1.isoformat(), "duracao_s": round((t1 - t0).total_seconds(), 1),
            "resultado": resultado, "classe_sugerida": classe, "classe": classe, "prova": texto,
            "criterios": [{"criterio": n, "ok": ok} for n, ok in ck],
            "chamadas_modelo": len(prova["chamadas_modelo"]),
            "chamadas_por_papel": {p: sum(1 for c in prova["chamadas_modelo"] if c["papel"] == p) for p in {c["papel"] for c in prova["chamadas_modelo"]}},
            "modelos_usados": sorted({c["modelo"] for c in prova["chamadas_modelo"]}),
            "tokens_entrada": sum(c["tokens_entrada"] for c in prova["chamadas_modelo"]),
            "tokens_saida": sum(c["tokens_saida"] for c in prova["chamadas_modelo"]),
            "primeiro_pedido_tokens": prova["chamadas_modelo"][0]["tokens_entrada"] if prova["chamadas_modelo"] else None,
            "maior_pedido_tokens": max((c["tokens_entrada"] for c in prova["chamadas_modelo"]), default=None),
            "custo_usd": float(sum(Decimal(str(c["custo_usd"])) for c in prova["chamadas_modelo"])),
            "chamadas_ferramenta": prova["rastro"]["ferramenta.inicio"] or sum(1 for p in prova["passos"] if p["tipo"] == "ferramenta"),
            "pedidos_ao_modelo_rastro": prova["rastro"]["modelo.pedido"],
            "chamadas_mcp": len(mcp["chamadas"]),
            "rastro": prova["rastro"],
            "bateu_limite_429": bool(limite) or prova["rastro"]["erros_de_limite"] > 0, "esperas_429_s": sum((e["d"]["parametros"] or {}).get("segundos", 0) for e in limite),
            "erros_sse": [e["d"] for e in ouv.eventos if e["ev"] == "erro"],
        })
        (pasta / "eventos.json").write_text(json.dumps(ouv.eventos, ensure_ascii=False, indent=1, default=str), "utf-8")
        (pasta / "prova.json").write_text(json.dumps({**prova, "mcp": mcp}, ensure_ascii=False, indent=1, default=str), "utf-8")
    except Exception as erro:  # a execução vira "não executado", nunca some
        reg.update({"resultado": "nao_executado", "classe": "transporte", "erro_executor": f"{type(erro).__name__}: {erro}"})
    finally:
        servidor.terminate()
        if reg.get("bot_id"):  # bancada limpa: o prompt leva a lista de colegas (baseline.md §4.1)
            r = await api.req("DELETE", f"/agentes/{reg['bot_id']}")
            reg["bot_apagado"] = r.status_code == 204
        await api.fechar()
    (pasta / "registro.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1, default=str), "utf-8")
    print(f"{fid} r{rodada}: {reg.get('resultado')} classe={reg.get('classe') or '-'} {reg.get('duracao_s', '?')} s | {reg.get('prova', reg.get('erro_executor', ''))}")
    return reg


FERRAMENTAS_BOT_PC = ["computador_observar", "computador_agir"]  # computador_abrir_programa vem junto


async def criar_bot_pc() -> None:
    """Bot das tarefas de tela (G01–G10, R1, R3). Depois, no app de desktop: Configurações → Computador → liberar."""
    api, est = await entrar()
    bot = await api.json("POST", "/agentes", 201, json={
        "nome": "BancadaPC", "funcao": "Bot de bancada de tela (baseline 0.5)",
        "papel": PAPEL_BOT + " Você controla o computador do usuário (alvo pc_usuario).",
        "ferramentas": FERRAMENTAS_BOT_PC})
    await api.json("PATCH", f"/agentes/{bot['id']}", json={"provedor_id": est["provedor_id"], "modelo": MODELO_FIXO,
                                                            "raciocinio": "auto", "permissao": "perguntar"})
    est["bot_pc_id"] = bot["id"]
    ESTADO.write_text(json.dumps(est, indent=1), "utf-8")
    print("bot BancadaPC:", bot["id"], "| ferramentas:", bot.get("ferramentas"), "| modelo fixo:", MODELO_FIXO)
    await api.fechar()


async def nova_g(tarefa: str, rodada: int) -> None:
    """Uma execução de tela = um bot NOVO (conversa e memória limpas), com o modelo fixo. Copia o pedido exato
    para a área de transferência; o Heitor libera o bot no PC (Configurações → Computador) e cola no chat dele."""
    import fixtures_gui as G

    api, est = await entrar()
    nome = f"{tarefa}r{rodada}x{agora().strftime('%H%M')}"
    bot = await api.json("POST", "/agentes", 201, json={
        "nome": nome, "funcao": "Bot de bancada de tela (baseline 0.5)",
        "papel": PAPEL_BOT + " Você controla o computador do usuário (alvo pc_usuario).",
        "ferramentas": FERRAMENTAS_BOT_PC})
    await api.json("PATCH", f"/agentes/{bot['id']}", json={"provedor_id": est["provedor_id"], "modelo": MODELO_FIXO,
                                                            "raciocinio": "auto", "permissao": "perguntar"})
    est["bot_g_atual"] = bot["id"]
    est["tarefa_g_atual"] = f"{tarefa}-r{rodada}"
    ESTADO.write_text(json.dumps(est, indent=1), "utf-8")
    pedido = G.PEDIDOS_G[tarefa]
    tmp = ESTADO.parent / "pedido.txt"
    tmp.write_text(pedido, "utf-8")
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Set-Clipboard -Value (Get-Content -Raw -Encoding UTF8 '{tmp}')"], check=False)
    print(f"bot {nome} criado ({bot['id']}). Libere-o em Configurações → Computador e cole o pedido (já copiado):")
    print(pedido)
    await api.fechar()


async def registrar_g(tarefa: str, rodada: int, resultado: str, classe: str, prova: str, log_worker: Path | None) -> None:
    """Grava a execução G/R feita pelo Heitor no app: lê a ÚLTIMA conversa do BancadaPC (só leitura)."""
    api, est = await entrar()
    try:
        bot_id = est.get("bot_g_atual") or est["bot_pc_id"]
        conversa = (await sql("SELECT id::text AS id, criada_em FROM conversas WHERE agente_id = :g "
                              "ORDER BY criada_em DESC LIMIT 1", g=bot_id))[0]
        msgs = await sql("SELECT autor::text AS autor, criada_em FROM mensagens WHERE conversa_id = :c ORDER BY criada_em",
                         c=conversa["id"])
        t0, t1 = min(m["criada_em"] for m in msgs), max(m["criada_em"] for m in msgs)
        dados = await coletar(api, est, conversa["id"], bot_id, t0, t1, log_worker)
        reg = {"tarefa": tarefa, "rodada": rodada, "conversa_id": conversa["id"], "inicio": t0.isoformat(),
               "fim": t1.isoformat(), "duracao_s": round((t1 - t0).total_seconds(), 1), "resultado": resultado,
               "classe": classe, "prova": prova, "modelo_fixo": MODELO_FIXO,
               "modelos_usados": sorted({c["modelo"] for c in dados["chamadas_modelo"]}),
               "chamadas_modelo": len(dados["chamadas_modelo"]), "pedidos_ao_modelo_rastro": dados["rastro"]["modelo.pedido"],
               "chamadas_ferramenta": dados["rastro"]["ferramenta.inicio"], "ferramentas": dados["rastro"]["ferramentas"],
               "tokens_entrada": sum(c["tokens_entrada"] for c in dados["chamadas_modelo"]),
               "tokens_saida": sum(c["tokens_saida"] for c in dados["chamadas_modelo"]),
               "custo_usd": float(sum(Decimal(str(c["custo_usd"])) for c in dados["chamadas_modelo"])),
               "bateu_limite_429": dados["rastro"]["erros_de_limite"] > 0,
               "cartoes": dados["aprovacoes"], "resposta_final": _resposta(dados)[:600]}
        pasta = EXECUCOES / f"{tarefa}-r{rodada}-{agora().strftime('%Y%m%dT%H%M%S')}"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "registro.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1, default=str), "utf-8")
        (pasta / "prova.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1, default=str), "utf-8")
        print(json.dumps({k: reg[k] for k in ("tarefa", "rodada", "resultado", "classe", "duracao_s", "chamadas_modelo",
                                              "chamadas_ferramenta", "tokens_entrada", "bateu_limite_429", "modelos_usados")},
                         ensure_ascii=False))
    finally:
        await api.fechar()


PEDIDO_WIKIPEDIA = ("Abra a página inicial da Wikipédia em português, use o campo de busca para procurar Santos "
                    "Dumont, abra o artigo e me diga o título que apareceu na página.")


async def reproduzir_wikipedia(rodada: int, log_worker: Path | None) -> dict:
    """Falha real R2 (log/2026-11-22.md): pedido exato, na conversa da Sora, com o modelo fixo."""
    marca = agora().strftime("%Y%m%dT%H%M%S")
    pasta = EXECUCOES / f"R2-wikipedia-r{rodada}-{marca}"
    pasta.mkdir(parents=True, exist_ok=True)
    api, est = await entrar()
    reg: dict[str, Any] = {"tarefa": "R2-wikipedia", "rodada": rodada, "inicio": agora().isoformat(),
                           "modelo_fixo": MODELO_FIXO, "turnos": [], "cartoes": [], "perguntas": []}
    try:
        sora = await api.json("GET", "/agentes/sora")
        t0 = agora()
        conversa = await api.json("POST", "/conversas", 201, json={"agente_id": sora["id"], "texto": PEDIDO_WIKIPEDIA, "anexos": []})
        reg["conversa_id"], reg["agente_id"] = conversa["id"], sora["id"]
        ouv = Ouvinte(api, conversa["id"])
        reg["turnos"].append(await rodar_turno(api, ouv, sora["id"], Turno(PEDIDO_WIKIPEDIA), 0, reg))
        await asyncio.sleep(3)
        t1 = agora()
        ouv.fechar()
        prova = await coletar(api, est, conversa["id"], sora["id"], t0, t1, log_worker)
        abas = await sql("SELECT url, titulo, usada_em::text AS usada_em FROM abas_navegador WHERE agente_id = :g "
                         "AND usada_em >= :a ORDER BY usada_em", g=sora["id"], a=t0)
        ferramentas = prova["rastro"]["ferramentas"] or [p["ferramenta"] for p in prova["passos"] if p["tipo"] == "ferramenta"]
        resp = sem_acento(_resposta(prova))
        ck = [
            ("usou o navegador interativo (não só busca)", any(f and f.startswith("navegador_") for f in ferramentas)),
            ("aba final no artigo Santos_Dumont (banco)", any("pt.wikipedia.org/wiki/santos_dumont" in (a["url"] or "").lower() for a in abas)),
            ("título da aba contém Santos Dumont (banco)", any("santos dumont" in sem_acento(a["titulo"] or "") for a in abas)),
            ("resposta cita o título Santos Dumont", "santos dumont" in resp),
        ]
        resultado, classe = classificar(ck, reg, prova)
        reg.update({"fim": t1.isoformat(), "duracao_s": round((t1 - t0).total_seconds(), 1), "resultado": resultado,
                    "classe_sugerida": classe, "classe": classe,
                    "prova": "; ".join(f"{'✔' if ok else '✘'} {n}" for n, ok in ck),
                    "ferramentas_usadas": ferramentas, "abas": abas,
                    "chamadas_modelo": len(prova["chamadas_modelo"]),
                    "modelos_usados": sorted({c["modelo"] for c in prova["chamadas_modelo"]}),
                    "tokens_entrada": sum(c["tokens_entrada"] for c in prova["chamadas_modelo"]),
                    "tokens_saida": sum(c["tokens_saida"] for c in prova["chamadas_modelo"]),
                    "chamadas_ferramenta": len(ferramentas), "rastro": prova["rastro"],
                    "bateu_limite_429": prova["rastro"]["erros_de_limite"] > 0,
                    "resposta_final": _resposta(prova)[:600]})
        (pasta / "prova.json").write_text(json.dumps({**prova, "abas": abas}, ensure_ascii=False, indent=1, default=str), "utf-8")
        (pasta / "eventos.json").write_text(json.dumps(ouv.eventos, ensure_ascii=False, indent=1, default=str), "utf-8")
    except Exception as erro:
        reg.update({"resultado": "nao_executado", "classe": "transporte", "erro_executor": f"{type(erro).__name__}: {erro}"})
    finally:
        await api.fechar()
    (pasta / "registro.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1, default=str), "utf-8")
    print(f"R2 wikipedia r{rodada}: {reg.get('resultado')} classe={reg.get('classe') or '-'} {reg.get('duracao_s', '?')} s | "
          f"{reg.get('prova', reg.get('erro_executor', ''))}")
    return reg


def anotar(pasta: str, resultado: str, classe: str, nota: str) -> None:
    """Revisão humana de uma execução já gravada: guarda o que o executor sugeriu e o motivo da troca."""
    arq = EXECUCOES / pasta / "registro.json"
    reg = json.loads(arq.read_text("utf-8"))
    reg.setdefault("revisao", []).append({"em": agora().isoformat(), "de": [reg.get("resultado"), reg.get("classe")],
                                          "para": [resultado, classe], "nota": nota})
    reg["resultado"], reg["classe"] = resultado, classe
    arq.write_text(json.dumps(reg, ensure_ascii=False, indent=1, default=str), "utf-8")
    print(pasta, "->", resultado, classe)


def resumo() -> None:
    regs = sorted((json.loads(p.read_text("utf-8")) for p in EXECUCOES.glob("*/registro.json")),
                  key=lambda r: (r["tarefa"], r["rodada"], r.get("inicio", "")))
    print("| Tarefa | Rodada | Resultado | Classe | Duração (s) | Modelo/ferr./MCP | Tokens in/out | 429 (espera s) | Prova |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in regs:
        print(f"| {r['tarefa']} | {r['rodada']} | {r.get('resultado')} | {r.get('classe') or '—'} | {r.get('duracao_s', '—')} | "
              f"{r.get('chamadas_modelo', '—')}/{r.get('chamadas_ferramenta', '—')}/{r.get('chamadas_mcp', '—')} | "
              f"{r.get('tokens_entrada', '—')}/{r.get('tokens_saida', '—')} | {'sim' if r.get('bateu_limite_429') else 'não'} ({r.get('esperas_429_s', 0)}) | "
              f"{(r.get('prova') or r.get('erro_executor') or '').replace('|', '/')} |")


def pedidos() -> None:
    for fid, fx in FIXTURES.items():
        print(f"\n### {fid} — {fx.titulo}\n")
        if fx.anexos:
            print("Anexos: " + ", ".join(f"`docs/benchmarks/dados/{a}`" for a in fx.anexos) + "\n")
        for i, t in enumerate(fx.turnos, 1):
            print(f"**Turno {i}:**\n\n> {t.texto}\n")
            if t.resposta_pergunta:
                print(f"Pergunta do bot → responder **{t.resposta_pergunta}**.\n")
            if t.decisao_cartao != "permitir_uma_vez":
                print(f"Cartão \"Precisa de você\" → **{t.decisao_cartao}**.\n")
        if fx.cartao_esperado:
            print(f"Cartão/pergunta esperado: {fx.cartao_esperado}.\n")


async def principal() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["preparar", "limpar", "modelos", "rodar", "resumo", "pedidos", "wikipedia", "bot-pc", "nova-g", "registrar-g", "anotar"])
    ap.add_argument("tarefas", nargs="*")
    ap.add_argument("--vezes", type=int, default=3)
    ap.add_argument("--primeira-rodada", type=int, default=1)
    ap.add_argument("--log-worker", type=Path)
    ap.add_argument("--resultado", choices=["ok", "parcial", "falhou", "nao_executado"])
    ap.add_argument("--classe", default="")
    ap.add_argument("--prova", default="")
    ap.add_argument("--nota", default="")
    ap.add_argument("--repetir-429", type=int, default=2, help="repete a execução que terminou só por 429")
    a = ap.parse_args()
    if a.acao == "preparar":
        await preparar()
    elif a.acao == "modelos":
        await listar_modelos()
    elif a.acao == "limpar":
        await limpar_bots()
    elif a.acao == "resumo":
        resumo()
    elif a.acao == "pedidos":
        pedidos()
    elif a.acao == "bot-pc":
        await criar_bot_pc()
    elif a.acao == "nova-g":
        await nova_g(a.tarefas[0].upper(), a.primeira_rodada)
    elif a.acao == "registrar-g":
        await registrar_g(a.tarefas[0], a.primeira_rodada, a.resultado, a.classe, a.prova, a.log_worker)
    elif a.acao == "anotar":
        anotar(a.tarefas[0], a.resultado, a.classe, a.nota)
    elif a.acao == "wikipedia":
        for n in range(a.primeira_rodada, a.primeira_rodada + a.vezes):
            await reproduzir_wikipedia(n, a.log_worker)
    else:
        if "COLOCAR_SHA" in URL_PAGINAS:
            sys.exit("Defina BASELINE_PAGINAS_SHA (commit que tem docs/benchmarks/paginas/).")
        for fid in a.tarefas or list(FIXTURES):
            for n in range(a.primeira_rodada, a.primeira_rodada + a.vezes):
                for _tentativa in range(a.repetir_429 + 1):
                    reg = await executar(fid, n, a.log_worker)
                    so_429 = reg.get("classe") == "cota_provedor"
                    if not so_429 or _tentativa == a.repetir_429:
                        break
                    print(f"  {fid} r{n}: parou por limite do provedor (429); espera 90 s e repete (não conta como falha)")
                    await asyncio.sleep(90)


if __name__ == "__main__":
    if sys.platform == "win32":  # psycopg async não roda no ProactorEventLoop
        asyncio.run(principal(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(principal())
