"""Motorista do teste REAL do controle do PC (C3) — faz o papel do worker, sem modelo.

Fala com o app de desktop pelo canal de verdade (Redis → API → ponte Rust), com o mesmo ``ComputadorPcUsuario``
que o worker usa. Quem decide os cartões "Precisa de você" é o teste (pela API, como o usuário).

Rodar de dentro de ``backend/`` (usa o .env de lá):
    PYTHONPATH=. uv run python ../app/qa/pc_real_driver.py observar <usuario_id> <bot_id> <saida.png>
    PYTHONPATH=. uv run python ../app/qa/pc_real_driver.py agir <usuario_id> <bot_id> '<json da ação>' [espera_cartao_s]

A ação é um ``AcaoComputador`` em JSON, mais dois campos do teste: ``janela_programa`` (ex.: "notepad.exe":
resolve a janela dessa programa na observação e usa o centro dela) e ``ponto`` ([x, y] da última captura).
Saída: uma linha JSON ``{"ok": bool, ...}``; nunca imprime o texto digitado.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from app.computador.interface import AcaoComputador, AcaoResolvida
from app.computador.pc_usuario import ProvedorPcUsuario
from app.ferramentas.base import ErroFerramenta


def _resumo_janelas(obs) -> list[dict]:
    return [
        {
            "id": j.id_nativo,
            "programa": j.programa,
            "titulo": j.titulo,
            "ativa": j.ativa,
            "pos": [j.x, j.y, j.largura, j.altura],
        }
        for j in obs.janelas
    ]


async def _computador(usuario: str, bot: str, espera: float):
    provedor = ProvedorPcUsuario(espera_cartao_s=espera)
    c = await provedor.obter(UUID(usuario), UUID(bot))
    c.intervalo_cartao_s = 0.5
    return c


async def observar(usuario: str, bot: str, saida: str) -> dict:
    c = await _computador(usuario, bot, 30)
    obs = await c.observar()
    Path(saida).write_bytes(obs.tela.png)
    arvore = obs.arvore or []
    return {
        "ok": True,
        "tela": [obs.tela.largura, obs.tela.altura],
        "png_bytes": len(obs.tela.png),
        "janelas": _resumo_janelas(obs),
        "arvore_n": len(arvore),
        "arvore": [
            {k: e.get(k) for k in ("ref", "papel", "nome", "valor", "estados", "centro") if e.get(k) not in (None, "", [])}
            for e in arvore[:25]
        ],
    }


async def agir(usuario: str, bot: str, bruto: str, espera: float) -> dict:
    dados = json.loads(bruto)
    programa = dados.pop("janela_programa", None)
    ponto = dados.pop("ponto", None)
    if ponto and dados.get("tipo") in {"clicar", "clique_duplo", "clicar_direito"}:
        dados["x"], dados["y"] = ponto  # o validador do AcaoComputador pede x/y (ou ref) nos cliques
    acao = AcaoComputador(**dados)
    c = await _computador(usuario, bot, espera)
    janela = None
    if programa:
        obs = await c.observar()
        janela = next((j for j in obs.janelas if j.programa == programa), None)
        if janela is None:
            return {"ok": False, "erro": f"janela de {programa} não achada", "janelas": _resumo_janelas(obs)}
        if ponto is None and acao.tipo in {"clicar", "clique_duplo", "clicar_direito"}:
            ponto = janela.centro
    resolvida = AcaoResolvida(
        acao=acao,
        janela=janela,
        tecla=acao.tecla,
        ponto=tuple(ponto) if ponto else None,
    )
    try:
        await c.agir(resolvida)
    except ErroFerramenta as erro:
        return {"ok": False, "erro": str(erro)}
    return {"ok": True}


async def main() -> None:
    comando = sys.argv[1]
    try:
        if comando == "observar":
            r = await observar(sys.argv[2], sys.argv[3], sys.argv[4])
        elif comando == "agir":
            espera = float(sys.argv[5]) if len(sys.argv) > 5 else 40.0
            r = await agir(sys.argv[2], sys.argv[3], sys.argv[4], espera)
        else:
            r = {"ok": False, "erro": f"comando desconhecido: {comando}"}
    except ErroFerramenta as erro:
        r = {"ok": False, "erro": str(erro)}
    print("RESULTADO " + json.dumps(r, ensure_ascii=False))


asyncio.run(main())
