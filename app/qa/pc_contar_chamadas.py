"""Vela-12: chamadas ao modelo e ferramentas de um turno (para a aceitação do C3 ao vivo).

Rodar de dentro de ``backend/``:
    PYTHONPATH=. uv run python ../app/qa/pc_contar_chamadas.py <usuario_id> <inicio_iso> [fim_iso]

Lê ``chamadas_modelo`` (papel, modelo, tokens, latência) e o checkpoint do bot não é lido: as
ferramentas vêm do rastro do painel (``passos`` com o id do turno) quando houver. Não imprime
texto digitado nem conteúdo de mensagem.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime

from sqlalchemy import text

from app.ferramentas.infra import abrir_sessao


async def main() -> None:
    usuario = sys.argv[1]
    inicio = datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00"))
    fim = datetime.fromisoformat(sys.argv[3].replace("Z", "+00:00")) if len(sys.argv) > 3 else None
    filtro = "usuario_id = :u and criado_em >= :i" + (" and criado_em <= :f" if fim else "")
    params = {"u": usuario, "i": inicio, **({"f": fim} if fim else {})}
    async with abrir_sessao() as s:
        linhas = (
            await s.execute(
                text(
                    "select criado_em, papel, modelo, tokens_entrada, tokens_saida, latencia_ms "
                    f"from chamadas_modelo where {filtro} order by criado_em"
                ),
                params,
            )
        ).all()
    total_ms = 0
    for l in linhas:
        total_ms += l[5]
        print(f"{l[0]:%H:%M:%S} {l[1]:<10} {l[2]:<28} in={l[3]:>6} out={l[4]:>5} {l[5]:>6} ms")
    print(f"CHAMADAS {len(linhas)}  latencia_somada_ms {total_ms}")
    por_papel: dict[str, int] = {}
    for l in linhas:
        por_papel[l[1]] = por_papel.get(l[1], 0) + 1
    print("POR_PAPEL", por_papel)


asyncio.run(main())
