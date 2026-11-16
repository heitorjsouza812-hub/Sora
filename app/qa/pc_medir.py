"""Medidor do controle do PC (C3, Vela-12): roda um roteiro de passos pelo MESMO caminho do bot.

``ServicoComputador`` (observar → agir → conferir) → ``ComputadorPcUsuario`` → canal Redis → API →
ponte Rust do app de desktop de verdade. Sem modelo: os passos vêm de um JSON. Mede o tempo de
cada passo e o tamanho do texto que o modelo receberia (proxy de tokens).

Rodar de dentro de ``backend/`` (usa o .env de lá):
    PYTHONPATH=. uv run python ../app/qa/pc_medir.py <usuario_id> <bot_id> <roteiro.json> [saida.json]

Roteiro: lista de passos ``{"op": "observar"}``, ``{"op": "agir", "acoes": [AcaoComputador…]}``,
``{"op": "abrir", "programa": "excel"}`` (só com o C3 da Vela-12) ou ``{"op": "liberar",
"programa": "excel.exe"}`` (dá "Permitir uma vez" direto no canal, como se o usuário tivesse
decidido o cartão: o teste mede o bot, não o tempo de clique do usuário).
Nunca imprime o texto digitado nem a árvore inteira.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

from app.computador.interface import AcaoComputador, Alvo
from app.computador.pc_usuario import ProvedorPcUsuario
from app.computador.servico import ServicoComputador
from app.ferramentas.base import ContextoFerramenta, ErroFerramenta


async def main() -> None:
    usuario, bot, roteiro = UUID(sys.argv[1]), UUID(sys.argv[2]), json.loads(Path(sys.argv[3]).read_text("utf-8"))
    from app.ferramentas.ambiente import redis_dos_eventos

    redis = redis_dos_eventos()

    async def publicar(evento, usuario_id) -> None:  # o painel não importa aqui
        return None

    servico = ServicoComputador(provedores={Alvo.PC_USUARIO: ProvedorPcUsuario()}, redis=redis, publicar=publicar)
    contexto = ContextoFerramenta(usuario_id=usuario, agente_id=bot, conversa_id=uuid4(), permissao="perguntar")
    resultados = []
    inicio_total = time.perf_counter()
    for i, passo in enumerate(roteiro, start=1):
        op = passo["op"]
        t0 = time.perf_counter()
        ok, texto = True, ""
        try:
            if op == "observar":
                texto = await servico.observar(contexto, Alvo.PC_USUARIO)
            elif op == "agir":
                acoes = [AcaoComputador(**a) for a in passo["acoes"]]
                texto = await servico.agir(contexto, acoes, Alvo.PC_USUARIO)
            elif op == "abrir":
                texto = await servico.abrir_programa(contexto, passo["programa"], Alvo.PC_USUARIO)
            elif op == "liberar":
                from app.computador.pc_usuario_canal import CanalPc

                await CanalPc(redis).permitir_uma_vez(usuario, bot, passo["programa"])
                texto = "liberado"
            else:
                raise ValueError(op)
        except ErroFerramenta as erro:
            ok, texto = False, str(erro)
        ms = round((time.perf_counter() - t0) * 1000)
        resumo = {
            "passo": i,
            "op": op,
            "ok": ok,
            "ms": ms,
            "chars_para_o_modelo": len(texto),
            "conferencia": next((l for l in texto.splitlines() if "Conferência" in l or "ação(ões)" in l), "")[:160],
        }
        if not ok:
            resumo["erro"] = texto[:300]
        if passo.get("mostrar"):
            resumo["texto"] = texto[: int(passo["mostrar"])]
        resultados.append(resumo)
        print(json.dumps(resumo, ensure_ascii=False), flush=True)
    total = round((time.perf_counter() - inicio_total) * 1000)
    saida = {"total_ms": total, "passos": resultados}
    print("TOTAL_MS", total)
    if len(sys.argv) > 4:
        Path(sys.argv[4]).write_text(json.dumps(saida, ensure_ascii=False, indent=2), "utf-8")


asyncio.run(main())
